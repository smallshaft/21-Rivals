"""
Correlation-aware optimizer ("v2").

Why: both players get the SAME cards as long as they make the same decisions.
If you hit blackjack on hand 1, your opponent (still in sync) also hit
blackjack, so their chips went up by 1.5x whatever THEY bet.  The v1 optimizer
treated the opponent's final score as independent of your cards; this one doesn't.

How:
1. Scenarios.  Millions of matches are played on the real shared-shoe engine.
   In each one, "you" play basic strategy and we record your result on each hand
   (in units of your bet), and the opponent plays its own strategy from the same
   shoe; we record their chips after every hand.
2. Result-history tree.  Your result each hand is put into one of 6 classes:
     0 lost 2+ units (lost a double/split)   1 lost   2 push
     3 won 1 unit   4 blackjack   5 won 2+ units (won a double/split)
   A node is the sequence of classes so far (hand 1 has 1 node, hand 5 has 6^4).
   At every node we know, from the scenarios, the exact probability
   distribution of the opponent's chips GIVEN what happened to you: e.g. after
   "blackjack" the opponent almost surely also gained; after "won by standing
   on 16" a casual who hit 16 may have busted.  Bet size, play style and
   whether they've drifted out of sync are all averaged in correctly.
3. Dynamic program over (node, your chips): the bet at each node and chip
   count maximizes 0.8*P(win) - P(loss) given that conditional opponent
   distribution and the probabilities of your next result.
   Rare histories (< MIN_COUNT scenarios) back off to their parent node.

In-hand play is basic strategy (v1's in-hand deviations were measured worth
~0, and changing decisions breaks the "same cards" link).  No side stakes, no
insurance in v2.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np
from numba import njit, prange

from . import core
from .config import Settings, MODEL_KEYS, RESULTS_DIR
from .strategy import build_tables, Tables
from . import optimizer as O

NCLS = 6
OFF = core.NODE_OFF            # [0,1,7,43,259,1555,9331]
NDEC = int(OFF[5])             # 1555 decision nodes (depth 0..4)
NALL = int(OFF[6])             # + 7776 leaves (depth 5)
CMAX = 8000.0
NC = int(CMAX / core.CHIP) + 1  # chip grid 0..8000 step 2.5
NB = NC + 1                    # opponent histogram bins (+ overflow)
MIN_COUNT = 400
CACHE = os.path.join(RESULTS_DIR, "cache")
CLASS_NAMES = ["lost a double/split", "lost", "push", "won", "blackjack", "won a double/split"]


@dataclass
class TreePlan:
    key: str
    bet: np.ndarray      # [NDEC, NC] bet for (node, chips)
    W: np.ndarray        # [NDEC, NC] P(win) under the plan
    L: np.ndarray        # [NDEC, NC] P(loss)
    V: np.ndarray        # [NDEC, NC] objective
    count: np.ndarray    # [NALL] scenarios per node
    opp_q: np.ndarray    # [NDEC, 5] opponent chips quantiles 10/25/50/75/90 at node
    opp_last: np.ndarray  # [NDEC, 3] P(opp gained / same / lost) on the last hand
    opp_type: np.ndarray  # [NDEC, ntypes] posterior over opponent types
    types: list

    def save(self, path):
        np.savez_compressed(path, key=self.key, bet=self.bet.astype(np.float32), W=self.W, L=self.L,
                            V=self.V, count=self.count, opp_q=self.opp_q, opp_last=self.opp_last,
                            opp_type=self.opp_type, types=np.array(self.types))

    @staticmethod
    def load(path):
        z = np.load(path)
        return TreePlan(str(z["key"]), z["bet"], z["W"], z["L"], z["V"], z["count"], z["opp_q"],
                        z["opp_last"], z["opp_type"], [str(t) for t in z["types"]])

    def engine_tables(self):
        b = self.bet.astype(np.float64)
        return b, b, b, np.zeros((6, 4))


def node_id(depth, code):
    return int(OFF[depth]) + int(code)


def history_code(results):
    code = 0
    for x in results:
        code = code * NCLS + int(core.xclass(float(x)))
    return code


# ----------------------------------------------------------------------------
# scenarios
# ----------------------------------------------------------------------------
def tree_player_params(jitter=0.0):
    P = core.ZP.copy()
    P[17] = 1.0   # no side stakes
    P[18] = 1.0   # basic-strategy play, no insurance
    P[19] = 1.0   # tree mode
    P[12] = jitter
    return P


def scenarios_for(settings: Settings, T: Tables, key: str, n: int, seed: int, sc_tabs=None):
    """(X, O, OT) for one opponent type, cached on disk."""
    import hashlib, json
    from dataclasses import asdict
    os.makedirs(CACHE, exist_ok=True)
    # depends on rules + this opponent's profile only (not the mix), so sweeps can re-weight
    blob = json.dumps({"rules": asdict(settings.rules),
                       "prof": settings.profiles.get(key, key)}, sort_keys=True)
    h = hashlib.sha1(blob.encode()).hexdigest()[:10]
    path = os.path.join(CACHE, f"scen_{h}_{key}_{n}_{seed}.npz")
    if os.path.exists(path):
        z = np.load(path)
        return z["X"], z["O"], z["OT"]
    if key == "sharp_c":
        P = core.ZP.copy(); P[12] = 0.30
        tabs = sc_tabs
        t = core.T_OPT
    else:
        P = settings.profile(key).as_params()
        tabs = O.dummy_plan_arrays()
        t = core.T_PARAM
    X, Ov, OT = core.gen_scenarios(n, seed, 64, t, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd, *tabs)
    np.savez(path, X=X, O=Ov, OT=OT)
    return X, Ov, OT


# ----------------------------------------------------------------------------
# DP over the result-history tree
# ----------------------------------------------------------------------------
@njit(parallel=True, cache=True)
def dp_tree(xprob, hist, eff, objective, minbet):
    """xprob[NDEC,17]: P(my next result = (bin-8)/2) at each decision node (backed off).
    hist[NALL,NB]: weighted opponent final-chip histogram per node; eff[NALL]: backoff node."""
    V = np.zeros((NDEC, NC), dtype=np.float32)
    W = np.zeros((NDEC, NC), dtype=np.float32)
    L = np.zeros((NDEC, NC), dtype=np.float32)
    B = np.zeros((NDEC, NC), dtype=np.float32)
    for d in range(4, -1, -1):
        lo = OFF[d]
        hi = OFF[d + 1]
        for nd in prange(lo, hi):
            code = nd - lo
            Vc = np.empty((NCLS, NC))
            Wc = np.empty((NCLS, NC))
            Lc = np.empty((NCLS, NC))
            for k in range(NCLS):
                ch = OFF[d + 1] + code * NCLS + k
                if d == 4:
                    e = eff[ch]
                    h = hist[e]
                    tot = h.sum()
                    cum = 0.0
                    for ci in range(NC):
                        less = cum / tot
                        greater = (tot - cum - h[ci]) / tot
                        cum += h[ci]
                        Wc[k, ci] = less
                        Lc[k, ci] = greater
                        Vc[k, ci] = less if objective == 1 else 0.8 * less - greater
                else:
                    for ci in range(NC):
                        Vc[k, ci] = V[ch, ci]
                        Wc[k, ci] = W[ch, ci]
                        Lc[k, ci] = L[ch, ci]
            p = xprob[nd]
            cls = np.empty(17, dtype=np.int64)
            for j in range(17):
                cls[j] = core.xclass((j - 8) / 2.0)
            mo = np.empty(200)
            for ci in range(NC):
                c = ci * core.CHIP
                if c < minbet:
                    V[nd, ci] = Vc[2, ci]
                    W[nd, ci] = Wc[2, ci]
                    L[nd, ci] = Lc[2, ci]
                    B[nd, ci] = 0.0
                    continue
                nm = core._main_options(c, mo)
                best = -1e18
                bb = 10.0
                for i in range(nm):
                    b = mo[i]
                    ev = 0.0
                    for j in range(17):
                        if p[j] <= 0.0:
                            continue
                        x = (j - 8) / 2.0
                        ix = int((c + b * x) / core.CHIP + 0.5)
                        if ix >= NC:
                            ix = NC - 1
                        if ix < 0:
                            ix = 0
                        ev += p[j] * Vc[cls[j], ix]
                    if ev > best + 1e-9:
                        best = ev
                        bb = b
                w = 0.0
                l = 0.0
                for j in range(17):
                    if p[j] <= 0.0:
                        continue
                    x = (j - 8) / 2.0
                    ix = int((c + bb * x) / core.CHIP + 0.5)
                    if ix >= NC:
                        ix = NC - 1
                    if ix < 0:
                        ix = 0
                    w += p[j] * Wc[cls[j], ix]
                    l += p[j] * Lc[cls[j], ix]
                V[nd, ci] = best
                W[nd, ci] = w
                L[nd, ci] = l
                B[nd, ci] = bb
    return B, V, W, L


def _wquantiles(vals, w, qs):
    o = np.argsort(vals)
    v, ww = vals[o], w[o]
    cw = np.cumsum(ww)
    cw /= cw[-1]
    return [float(v[min(np.searchsorted(cw, q), len(v) - 1)]) for q in qs]


def build_tree_plan(settings: Settings, n_per_type=3_000_000, seed=31, verbose=True, T=None) -> TreePlan:
    t0 = time.time()
    T = T or build_tables(settings.rules)
    log = (lambda *a: print(f"  [{time.time() - t0:5.0f}s]", *a, flush=True)) if verbose else (lambda *a: None)
    # opponent types used for optimization (the exact mirror always ties -> irrelevant)
    w = {k: float(settings.mix.get(k, 0.0)) for k in MODEL_KEYS if k != "sharp_b"}
    w = {k: v for k, v in w.items() if v > 0}
    if not w:
        w = {"sharp_a": 1.0}
    tot = sum(w.values())
    types = list(w)
    sc_tabs = None
    if "sharp_c" in w:
        J = O.joint_tables(T)
        pm = O.simulate_alone(T, core.T_PARAM, settings.profile("sharp_a").as_params(), 500_000, 3)
        sc_tabs = O.sharp_c_plan(settings, T, J, pm)
    Xs, Os, OTs, Ws, Ts = [], [], [], [], []
    for i, k in enumerate(types):
        X, Ov, OT = scenarios_for(settings, T, k, n_per_type, seed + 101 * MODEL_KEYS.index(k), sc_tabs)
        Xs.append(X); Os.append(Ov); OTs.append(OT)
        Ws.append(np.full(len(Ov), w[k] / tot / len(Ov), dtype=np.float64))
        Ts.append(np.full(len(Ov), i, dtype=np.int8))
        log(f"scenarios {k}: {len(Ov):,}")
    X = np.concatenate(Xs); Ov = np.concatenate(Os); OT = np.concatenate(OTs)
    wt = np.concatenate(Ws); ty = np.concatenate(Ts)
    del Xs, Os, OTs

    # result classes and node codes
    cls = np.zeros(X.shape, dtype=np.int64)
    cls[X <= -2] = 0
    cls[(X > -2) & (X < 0)] = 1
    cls[X == 0] = 2
    cls[(X > 0) & (X <= 1)] = 3
    cls[X == 1.5] = 4
    cls[X >= 2] = 5
    leaf = np.zeros(len(X), dtype=np.int64)
    for h in range(5):
        leaf = leaf * NCLS + cls[:, h]
    # node codes at each depth
    codes = [leaf // NCLS ** (5 - d) for d in range(6)]
    count = np.zeros(NALL, dtype=np.int64)
    for d in range(6):
        count[OFF[d]:OFF[d + 1]] = np.bincount(codes[d], minlength=NCLS ** d)
    # backoff: nearest ancestor with enough scenarios
    eff = np.arange(NALL)
    for d in range(1, 6):
        for code in range(NCLS ** d):
            nid = OFF[d] + code
            if count[nid] < MIN_COUNT:
                eff[nid] = eff[OFF[d - 1] + code // NCLS]
    # opponent final histograms, all nodes (weighted)
    ob = np.clip((Ov / core.CHIP).round().astype(np.int64), 0, NB - 1)
    ob[Ov > CMAX] = NB - 1
    hist = np.zeros((NALL, NB), dtype=np.float64)
    leafh = np.zeros((NCLS ** 5) * NB, dtype=np.float64)
    np.add.at(leafh, leaf * NB + ob, wt)
    hist[OFF[5]:] = leafh.reshape(NCLS ** 5, NB)
    del leafh
    for d in range(4, -1, -1):
        hist[OFF[d]:OFF[d + 1]] = hist[OFF[d + 1]:OFF[d + 2]].reshape(NCLS ** d, NCLS, NB).sum(axis=1)
    log("histograms built")
    # my next-result distribution at each decision node
    xprob = np.zeros((NDEC, 17))
    for d in range(5):
        xb = np.clip((X[:, d] * 2).round().astype(np.int64) + 8, 0, 16)
        acc = np.zeros(NCLS ** d * 17)
        np.add.at(acc, codes[d] * 17 + xb, wt)
        xprob[OFF[d]:OFF[d + 1]] = acc.reshape(NCLS ** d, 17)
    xprob_eff = np.zeros_like(xprob)
    for nd in range(NDEC):
        e = eff[nd]
        xprob_eff[nd] = xprob[e] / xprob[e].sum()
    obj = 1 if settings.objective == "winprob" else 0
    B, V, Wv, Lv = dp_tree(xprob_eff, hist.astype(np.float64), eff, obj, settings.rules.min_bet)
    log("DP solved")

    # display statistics: opponent chips after d hands at each node
    opp_q = np.zeros((NDEC, 5)); opp_last = np.zeros((NDEC, 3)); opp_type = np.zeros((NDEC, len(types)))
    order = np.argsort(leaf, kind="stable")
    sl = leaf[order]
    for d in range(5):
        div = NCLS ** (5 - d)
        bounds = np.searchsorted(sl, np.arange(NCLS ** d + 1) * div)
        for code in range(NCLS ** d):
            nd = OFF[d] + code
            e = eff[nd]
            if e != nd:   # sparse: use the backoff node's stats
                continue
            idx = order[bounds[code]:bounds[code + 1]]
            ww = wt[idx]
            if d == 0:
                chips = np.full(len(idx), 1000.0)
                last = np.zeros(len(idx))
            else:
                chips = OT[idx, d - 1].astype(np.float64)
                prev = OT[idx, d - 2] if d >= 2 else np.full(len(idx), 1000.0)
                last = chips - prev
            opp_q[nd] = _wquantiles(chips, ww, [0.1, 0.25, 0.5, 0.75, 0.9])
            s = ww.sum()
            opp_last[nd] = [ww[last > 0].sum() / s, ww[last == 0].sum() / s, ww[last < 0].sum() / s]
            for i in range(len(types)):
                opp_type[nd, i] = ww[ty[idx] == i].sum() / s
    for nd in range(NDEC):
        e = eff[nd]
        if e != nd:
            opp_q[nd], opp_last[nd], opp_type[nd] = opp_q[e], opp_last[e], opp_type[e]
    log("done")
    return TreePlan(settings.key(), B, Wv, Lv, V, count, opp_q, opp_last, opp_type, types)


def get_tree_plan(settings: Settings, verbose=True) -> TreePlan:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"tree_{settings.key()}.npz")
    if os.path.exists(path):
        return TreePlan.load(path)
    plan = build_tree_plan(settings, verbose=verbose)
    plan.save(path)
    return plan
