"""
Correlation-aware optimizer ("v2").

Why: both players get the SAME cards as long as they make the same decisions.
If you hit blackjack on hand 1, your opponent (still in sync) also hit
blackjack; if you doubled 10 vs 6 and the dealer busted, almost anyone did
the same thing and also won.  But if you stood on 16 vs 10, a casual opponent
may have hit instead, so their result is much less certain.

How:
1. Scenarios.  Millions of matches on the real shared-shoe engine.  "You" play
   basic strategy; for every hand we record what you SAW:
       your starting hand (BJ / pair / soft A2-A9 / hard 5-19),
       the dealer's upcard, your result (6 classes), how the dealer finished
       (17-21, bust, blackjack, didn't play out)
   -- about 16,800 possible situations -- and the opponent (playing their own
   style from the same shoe) has their chips recorded after every hand.
2. Situation -> opponent outcome.  For every situation we measure, over the
   simulated opponents, P(opponent gained / broke even / lost) on that hand and
   their average swing.  Rare situations borrow from similar ones (same start
   and result, any upcard; then same result and dealer finish).
3. Buckets.  Situations with similar opponent outcomes are clustered into
   8 buckets ("opponent almost surely won", "coin flip", "probably pushed"...).
4. History tree.  Your sequence of buckets so far is a node (8^4 nodes at hand
   5).  At every node we know, from the scenarios, the distribution of the
   opponent's chips.  A dynamic program over (node, your chips) picks each bet
   to maximize 0.8*P(win) - P(loss).  Rare nodes back off to their parent.

In-hand play is basic strategy (changing decisions breaks the same-cards link,
and v1's in-hand deviations were worth ~0).  No side stakes, no insurance.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict

import numpy as np
from numba import njit, prange

from . import core
from .config import Settings, MODEL_KEYS, RESULTS_DIR, CACHE_DIR
from .strategy import build_tables, Tables
from . import optimizer as O

NCLS = core.NCLS
OFF = core.NODE_OFF
NDEC = int(OFF[5])
NALL = int(OFF[6])
NKEYS = core.NKEYS
NSTART, NDCAT = core.NSTART, core.NDCAT
CMAX = 6000.0
NC = int(CMAX / core.CHIP) + 1
NB = NC + 1
MIN_COUNT = 400
KEY_MIN = 300
CACHE = CACHE_DIR
RESULT_NAMES = ["lost a double/split", "lost", "push", "won", "blackjack", "won a double/split"]
DEALER_NAMES = ["17", "18", "19", "20", "21", "bust", "blackjack", "didn't play out"]


def make_key(start, up, result_cls, dcat):
    return ((int(start) * 10 + (int(up) - 1)) * 6 + int(result_cls)) * NDCAT + int(dcat)


def split_key(k):
    dcat = k % NDCAT
    k //= NDCAT
    r = k % 6
    k //= 6
    return k // 10, k % 10 + 1, r, dcat


def start_cat_ranks(r1, r2):
    """Same as core.start_cat, from ranks (1 = Ace, 10 = ten/face)."""
    return int(core.start_cat((min(r1, 10) - 1) * 4, (min(r2, 10) - 1) * 4))


@dataclass
class TreePlan:
    key: str
    bet: np.ndarray       # [NDEC, NC]
    W: np.ndarray         # [NDEC, NC] P(win)
    L: np.ndarray         # [NDEC, NC] P(loss)
    V: np.ndarray
    count: np.ndarray     # [NALL]
    opp_q: np.ndarray     # [NDEC, 5]  opponent chips quantiles at node
    opp_last: np.ndarray  # [NDEC, 3]
    keymap: np.ndarray    # [NKEYS] situation -> bucket
    keystat: np.ndarray   # [NKEYS, 4] P(opp gained, even, lost), raw count
    poolmap: np.ndarray   # [6*NDCAT] bucket when the cards weren't entered
    poolstat: np.ndarray  # [6*NDCAT, 3]
    centroids: np.ndarray  # [NCLS, 3]
    types: list

    def save(self, path):
        # W/L stored as 16-bit fractions; V (internal objective) isn't needed after solving
        q = lambda a: np.round(np.clip(a, 0, 1) * 65535).astype(np.uint16)
        np.savez_compressed(path, key=self.key, bet=self.bet.astype(np.float32), W=q(self.W), L=q(self.L),
                            V=np.zeros(1, np.float32), count=self.count, opp_q=self.opp_q, opp_last=self.opp_last,
                            keymap=self.keymap, keystat=self.keystat, poolmap=self.poolmap,
                            poolstat=self.poolstat, centroids=self.centroids, types=np.array(self.types))

    @staticmethod
    def load(path):
        z = np.load(path)
        uq = lambda a: a.astype(np.float32) / 65535 if a.dtype == np.uint16 else a
        return TreePlan(str(z["key"]), z["bet"], uq(z["W"]), uq(z["L"]), z["V"], z["count"], z["opp_q"],
                        z["opp_last"], z["keymap"], z["keystat"], z["poolmap"], z["poolstat"],
                        z["centroids"], [str(t) for t in z["types"]])

    def engine_tables(self, keymap=None):
        """(bet, bet, bet, keymap-row) in the engine's plan-table slots (tree mode)."""
        b = self.bet.astype(np.float64)
        km = (self.keymap if keymap is None else keymap).astype(np.float64)[None, :]
        return b, b, b, km

    def bucket(self, cards, up, x, dcat):
        """Bucket for a finished hand. cards/up may be None if not entered."""
        r = int(core.xclass(float(x)))
        if cards and up:
            return int(self.keymap[make_key(start_cat_ranks(*cards[:2]), up, r, dcat)])
        return int(self.poolmap[r * NDCAT + dcat])

    def hand_stat(self, cards, up, x, dcat):
        r = int(core.xclass(float(x)))
        if cards and up:
            return self.keystat[make_key(start_cat_ranks(*cards[:2]), up, r, dcat), :3]
        return self.poolstat[r * NDCAT + dcat]


def node_id(depth, code):
    return int(OFF[depth]) + int(code)


def history_code(buckets):
    code = 0
    for b in buckets:
        code = code * NCLS + int(b)
    return code


def tree_player_params(jitter=0.0):
    P = core.ZP.copy()
    P[17] = 1.0   # no side stakes
    P[18] = 1.0   # basic-strategy play, no insurance
    P[19] = 1.0   # tree mode
    P[12] = jitter
    return P


# ----------------------------------------------------------------------------
# scenarios
# ----------------------------------------------------------------------------
def scenarios_for(settings: Settings, T: Tables, key: str, n: int, seed: int, sc_tabs=None):
    """(X, K, O, OT) for one opponent type; cached by rules + this opponent's profile."""
    os.makedirs(CACHE, exist_ok=True)
    blob = json.dumps({"rules": asdict(settings.rules), "prof": settings.profiles.get(key, key), "v": 3},
                      sort_keys=True)
    h = hashlib.sha1(blob.encode()).hexdigest()[:10]
    path = os.path.join(CACHE, f"scen3_{h}_{key}_{n}_{seed}.npz")
    if os.path.exists(path):
        z = np.load(path)
        return z["X"], z["K"], z["O"], z["OT"]
    if key == "sharp_c":
        P = core.ZP.copy(); P[12] = 0.30
        tabs, t = sc_tabs, core.T_OPT
    else:
        P = settings.profile(key).as_params()
        tabs, t = O.dummy_plan_arrays(), core.T_PARAM
    X, K, Ov, OT = core.gen_scenarios(n, seed, 64, t, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd, *tabs)
    np.savez(path, X=X, K=K, O=Ov, OT=OT)
    return X, K, Ov, OT


# ----------------------------------------------------------------------------
# situation statistics + buckets
# ----------------------------------------------------------------------------
def situation_stats(K, OT, wt):
    """Weighted per-situation opponent outcome sums: [NKEYS, 6] = w, w+, w0, w-, w*delta, raw count."""
    acc = np.zeros((NKEYS, 6))
    prev = np.full(len(K), 1000.0, dtype=np.float64)
    for h in range(K.shape[1]):
        d = OT[:, h].astype(np.float64) - prev
        prev = OT[:, h].astype(np.float64)
        k = K[:, h]
        acc[:, 0] += np.bincount(k, wt, NKEYS)
        acc[:, 1] += np.bincount(k, wt * (d > 0), NKEYS)
        acc[:, 2] += np.bincount(k, wt * (d == 0), NKEYS)
        acc[:, 3] += np.bincount(k, wt * (d < 0), NKEYS)
        acc[:, 4] += np.bincount(k, wt * d, NKEYS)
        acc[:, 5] += np.bincount(k, None, NKEYS)
    return acc


CLEAR = 0.90   # a hand is "clear" if >= 90% of in-sync opponents moved the same way you did
BUCKET_NAMES = ["lost a double/split", "lost (clear)", "lost (ambiguous)", "push",
                "won (clear)", "won (ambiguous)", "blackjack", "won a double/split"]


def make_buckets(acc1):
    """acc1: situation stats from HAND 1 only (both players always start in sync there),
    so they measure how ambiguous the situation itself is.
    Bucket = your result, with plain wins/losses split into clear vs ambiguous."""
    a5 = acc1.reshape(NSTART, 10, 6, NDCAT, 6)
    by_start = a5.sum(axis=1)                       # pooled over upcards
    by_rd = a5.sum(axis=(0, 1))                     # pooled over start + upcard
    eff = acc1.copy()
    k = np.arange(NKEYS)
    s, u, r, dc = split_key(k.copy())
    low = acc1[:, 5] < KEY_MIN
    eff[low] = by_start[s[low], r[low], dc[low]]
    low2 = eff[:, 5] < KEY_MIN
    eff[low2] = by_rd[r[low2], dc[low2]]
    w = np.maximum(eff[:, 0], 1e-300)
    pg, p0, pl = eff[:, 1] / w, eff[:, 2] / w, eff[:, 3] / w

    def bucket(r, pg, pl):
        out = np.select([r == 0, r == 2, r == 4, r == 5], [0, 3, 6, 7], -1)
        out = np.where(r == 1, np.where(pl >= CLEAR, 1, 2), out)
        out = np.where(r == 3, np.where(pg >= CLEAR, 4, 5), out)
        return out.astype(np.int64)

    keymap = bucket(r, pg, pl)
    pr = by_rd.reshape(-1, 6)
    pw = np.maximum(pr[:, 0], 1e-300)
    rr = np.arange(6 * NDCAT) // NDCAT
    poolmap = bucket(rr, pr[:, 1] / pw, pr[:, 3] / pw)
    keystat = np.stack([pg, p0, pl, acc1[:, 5]], axis=1)
    poolstat = np.stack([pr[:, 1] / pw, pr[:, 2] / pw, pr[:, 3] / pw], axis=1)
    cent = np.zeros((NCLS, 3))
    for c in range(NCLS):
        m = keymap == c
        if acc1[m, 0].sum() > 0:
            cent[c] = [acc1[m, i].sum() / acc1[m, 0].sum() for i in (1, 2, 3)]
    return keymap, keystat, poolmap, poolstat, cent


# ----------------------------------------------------------------------------
# DP over the bucket-history tree
# ----------------------------------------------------------------------------
@njit(parallel=True, cache=True)
def dp_tree(xprob, hist, eff, objective, minbet):
    """xprob[NDEC,17,NCLS]: P(my next result = (bin-8)/2 AND next bucket = k | node).
    hist[NALL,NB]: weighted opponent final-chip histogram per node; eff: backoff node."""
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
                    h = hist[eff[ch]]
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
            js = np.empty(17 * NCLS, dtype=np.int64)
            ks = np.empty(17 * NCLS, dtype=np.int64)
            ps = np.empty(17 * NCLS)
            ne = 0
            for j in range(17):
                for k in range(NCLS):
                    if p[j, k] > 0.0:
                        js[ne] = j
                        ks[ne] = k
                        ps[ne] = p[j, k]
                        ne += 1
            mo = np.empty(200)
            for ci in range(NC):
                c = ci * core.CHIP
                if c < minbet:
                    # can't bet: chips stay; the hand still "happens" for the opponent
                    v = 0.0; w = 0.0; l = 0.0
                    for e in range(ne):
                        v += ps[e] * Vc[ks[e], ci]
                        w += ps[e] * Wc[ks[e], ci]
                        l += ps[e] * Lc[ks[e], ci]
                    V[nd, ci] = v; W[nd, ci] = w; L[nd, ci] = l; B[nd, ci] = 0.0
                    continue
                nm = core._main_options(c, mo)
                best = -1e18
                bb = 10.0
                for i in range(nm):
                    b = mo[i]
                    ev = 0.0
                    for e in range(ne):
                        ix = int((c + b * (js[e] - 8) / 2.0) / core.CHIP + 0.5)
                        if ix >= NC:
                            ix = NC - 1
                        elif ix < 0:
                            ix = 0
                        ev += ps[e] * Vc[ks[e], ix]
                    if ev > best + 1e-9:
                        best = ev
                        bb = b
                w = 0.0
                l = 0.0
                for e in range(ne):
                    ix = int((c + bb * (js[e] - 8) / 2.0) / core.CHIP + 0.5)
                    if ix >= NC:
                        ix = NC - 1
                    elif ix < 0:
                        ix = 0
                    w += ps[e] * Wc[ks[e], ix]
                    l += ps[e] * Lc[ks[e], ix]
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


def build_tree_plan(settings: Settings, n_per_type=3_000_000, seed=31, verbose=True, T=None,
                    bucket_mode="situation") -> TreePlan:
    """bucket_mode 'situation' (default): buckets from what you saw each hand.
    'result': bucket = your result class only (used for the paper cheat sheet)."""
    t0 = time.time()
    T = T or build_tables(settings.rules)
    log = (lambda *a: print(f"  [{time.time() - t0:5.0f}s]", *a, flush=True)) if verbose else (lambda *a: None)
    w = {k: float(settings.mix.get(k, 0.0)) for k in MODEL_KEYS if k != "sharp_b"}   # mirror always ties
    w = {k: v for k, v in w.items() if v > 0} or {"sharp_a": 1.0}
    tot = sum(w.values())
    types = list(w)
    sc_tabs = None
    if "sharp_c" in w:
        J = O.joint_tables(T)
        pm = O.simulate_alone(T, core.T_PARAM, settings.profile("sharp_a").as_params(), 500_000, 3)
        sc_tabs = O.sharp_c_plan(settings, T, J, pm)
    Xs, Ks, Os, OTs, Ws = [], [], [], [], []
    for k in types:
        X, K, Ov, OT = scenarios_for(settings, T, k, n_per_type, seed + 101 * MODEL_KEYS.index(k), sc_tabs)
        Xs.append(X); Ks.append(K); Os.append(Ov); OTs.append(OT)
        Ws.append(np.full(len(Ov), w[k] / tot / len(Ov)))
        log(f"scenarios {k}: {len(Ov):,}")
    X = np.concatenate(Xs); K = np.concatenate(Ks); Ov = np.concatenate(Os); OT = np.concatenate(OTs)
    wt = np.concatenate(Ws)
    del Xs, Ks, Os, OTs

    acc1 = situation_stats(K[:, :1], OT[:, :1], wt)
    keymap, keystat, poolmap, poolstat, cent = make_buckets(acc1)
    if bucket_mode == "result":
        r = split_key(np.arange(NKEYS))[2]
        keymap = np.array([0, 0, 1, 2, 3, 3])[r].astype(np.int64)   # lost / push / won / BJ-or-won-2+
        poolmap = np.array([0, 0, 1, 2, 3, 3])[np.arange(6 * NDCAT) // NDCAT].astype(np.int64)
    log("situations bucketed")
    cls = keymap[K]                                   # [N,5]
    leaf = np.zeros(len(X), dtype=np.int64)
    for h in range(5):
        leaf = leaf * NCLS + cls[:, h]
    codes = [leaf // NCLS ** (5 - d) for d in range(6)]
    count = np.zeros(NALL, dtype=np.int64)
    for d in range(6):
        count[OFF[d]:OFF[d + 1]] = np.bincount(codes[d], minlength=NCLS ** d)
    eff = np.arange(NALL)
    for d in range(1, 6):
        nid = OFF[d] + np.arange(NCLS ** d)
        parent = eff[OFF[d - 1] + np.arange(NCLS ** d) // NCLS]
        eff[nid] = np.where(count[nid] < MIN_COUNT, parent, nid)
    ob = np.clip((Ov / core.CHIP).round().astype(np.int64), 0, NB - 1)
    ob[Ov > CMAX] = NB - 1
    hist = np.zeros((NALL, NB), dtype=np.float32)
    hist[OFF[5]:] = np.bincount(leaf * NB + ob, wt, (NCLS ** 5) * NB).reshape(NCLS ** 5, NB)
    for d in range(4, -1, -1):
        hist[OFF[d]:OFF[d + 1]] = hist[OFF[d + 1]:OFF[d + 2]].reshape(NCLS ** d, NCLS, NB).sum(axis=1)
    log("histograms built")
    xprob = np.zeros((NDEC, 17, NCLS))
    for d in range(5):
        xb = np.clip((X[:, d] * 2).round().astype(np.int64) + 8, 0, 16)
        a = np.bincount((codes[d] * 17 + xb) * NCLS + cls[:, d], wt, NCLS ** d * 17 * NCLS)
        xprob[OFF[d]:OFF[d + 1]] = a.reshape(NCLS ** d, 17, NCLS)
    xprob_eff = xprob[eff[:NDEC]]
    xprob_eff /= xprob_eff.sum(axis=(1, 2), keepdims=True)
    obj = 1 if settings.objective == "winprob" else 0
    B, V, Wv, Lv = dp_tree(xprob_eff, hist, eff, obj, settings.rules.min_bet)
    del hist
    log("DP solved")

    opp_q = np.zeros((NDEC, 5)); opp_last = np.zeros((NDEC, 3))
    order = np.argsort(leaf, kind="stable")
    sl = leaf[order]
    for d in range(5):
        div = NCLS ** (5 - d)
        bounds = np.searchsorted(sl, np.arange(NCLS ** d + 1) * div)
        for code in range(NCLS ** d):
            nd = OFF[d] + code
            if eff[nd] != nd:
                continue
            idx = order[bounds[code]:bounds[code + 1]]
            ww = wt[idx]
            if d == 0:
                chips = np.full(len(idx), 1000.0); last = np.zeros(len(idx))
            else:
                chips = OT[idx, d - 1].astype(np.float64)
                prev = OT[idx, d - 2] if d >= 2 else np.full(len(idx), 1000.0)
                last = chips - prev
            opp_q[nd] = _wquantiles(chips, ww, [0.1, 0.25, 0.5, 0.75, 0.9])
            s = ww.sum()
            opp_last[nd] = [ww[last > 0].sum() / s, ww[last == 0].sum() / s, ww[last < 0].sum() / s]
    for nd in range(NDEC):
        if eff[nd] != nd:
            opp_q[nd], opp_last[nd] = opp_q[eff[nd]], opp_last[eff[nd]]
    log("done")
    return TreePlan(settings.key(), B, Wv, Lv, V, count, opp_q, opp_last, keymap, keystat, poolmap,
                    poolstat, cent, types)


def get_tree_plan(settings: Settings, verbose=True, bucket_mode="situation") -> TreePlan:
    """Cached plan. A plan shipped in results/ for the default settings is used if present,
    so the first launch doesn't have to simulate millions of matches."""
    os.makedirs(CACHE, exist_ok=True)
    name = f"tree3_{bucket_mode}_{settings.key()}.npz"
    for path in (os.path.join(CACHE, name), os.path.join(RESULTS_DIR, name)):
        if os.path.exists(path):
            return TreePlan.load(path)
    plan = build_tree_plan(settings, n_per_type=3_000_000, verbose=verbose, bucket_mode=bucket_mode)
    plan.save(os.path.join(CACHE, name))
    return plan
