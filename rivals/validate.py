"""
Validation: brute-force simulation of full head-to-head matches with the exact
shared-shoe rule.  This is the ground truth for every number in the report.

    python -m rivals.validate            # full run (10M matches per matchup, ~30-60 min on a Mac)
    python -m rivals.validate --quick    # smoke test (~3 min)

Outputs: results/report.json, results/REPORT.md, results/sim_hist.npz
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time

import numpy as np

from . import core
from .config import (Settings, Rules, MODEL_KEYS, MODEL_NAMES, ENTRIES, BREAKEVEN,
                     RESULTS_DIR, Profile, DEFAULT_MIX)
from . import optimizer as O
from .strategy import build_tables, perfect_pairs_exact, four_card_total_exact
from . import corr

Z99 = 2.5758293035489
JITTER_P = core.ZP.copy()
JITTER_P[12] = 0.30      # +/-30% per-match bet scaling for match-aware stress opponents
SEED = 20261112


# ----------------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------------
def wilson(k, n, z=Z99):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def summarize(w, t, l):
    n = w + t + l
    W, T, L = w / n, t / n, l / n
    dec = w + l
    r = w / dec if dec else float("nan")
    lo, hi = wilson(w, dec) if dec else (float("nan"), float("nan"))
    ev = 0.8 * W - L                                   # profit per $1 entry
    var = (0.64 * W + L) - ev * ev
    se = math.sqrt(var / n)
    return {"n": int(n), "win": W, "tie": T, "loss": L, "dec_rate": r, "dec_ci99": [lo, hi],
            "ev_per_dollar": ev, "ev_ci99": [ev - Z99 * se, ev + Z99 * se],
            "profit_per_match": {str(e): ev * e for e in ENTRIES}}


def mixture(results: dict, weights: dict):
    """Combine per-model results with population weights (delta-method CI)."""
    ks = [k for k in weights if weights[k] > 0]
    tot = sum(weights[k] for k in ks)
    W = sum(weights[k] / tot * results[k]["win"] for k in ks)
    L = sum(weights[k] / tot * results[k]["loss"] for k in ks)
    T = 1 - W - L
    r = W / (W + L)
    var_r = 0.0
    var_ev = 0.0
    for k in ks:
        a = weights[k] / tot
        n = results[k]["n"]
        wi, li = results[k]["win"], results[k]["loss"]
        vw, vl, cwl = wi * (1 - wi) / n, li * (1 - li) / n, -wi * li / n
        gW, gL = L / (W + L) ** 2, -W / (W + L) ** 2
        var_r += a * a * (gW * gW * vw + gL * gL * vl + 2 * gW * gL * cwl)
        var_ev += a * a * (0.64 * vw + vl - 1.6 * cwl)
    ev = 0.8 * W - L
    se_r, se_ev = math.sqrt(var_r), math.sqrt(var_ev)
    return {"win": W, "tie": T, "loss": L, "dec_rate": r,
            "dec_ci99": [r - Z99 * se_r, r + Z99 * se_r],
            "ev_per_dollar": ev, "ev_ci99": [ev - Z99 * se_ev, ev + Z99 * se_ev],
            "profit_per_match": {str(e): ev * e for e in ENTRIES}}


# ----------------------------------------------------------------------------
# running matchups
# ----------------------------------------------------------------------------
class Ctx:
    """Everything needed to run sims for one rule set.

    A *strategy* is (ptype, P, tables).  'v2' is the correlation-aware plan
    (corr.py, used by the app); 'v1' is the original plan that treated the
    opponent's cards as independent (optimizer.py), kept for comparison."""

    def __init__(self, settings: Settings, n_opp=1_000_000, n_scen=3_000_000, verbose=True):
        self.s = settings
        self.T = build_tables(settings.rules)
        self.J = O.joint_tables(self.T)
        self.pmfs = O.model_pmfs_for(settings, self.T, self.J, n_opp)
        self.sc = O.sharp_c_plan(settings, self.T, self.J, self.pmfs[MODEL_KEYS.index("sharp_a")])
        self.n_scen = n_scen
        self.verbose = verbose

    def _settings(self, mix):
        s2 = Settings.from_dict(json.loads(self.s.to_json()))
        s2.mix = {k: float(mix.get(k, 0.0)) for k in MODEL_KEYS}
        return s2

    def plan_for(self, mix):
        return O.build_plan(self._settings(mix), T=self.T, J=self.J, model_pmfs=self.pmfs, verbose=False)

    def tree_for(self, mix):
        return corr.build_tree_plan(self._settings(mix), n_per_type=self.n_scen, T=self.T, verbose=False)

    @staticmethod
    def v1(plan, P=None):
        return (core.T_OPT, core.ZP if P is None else P, (plan.bet, plan.pp, plan.fc, plan.Vall))

    @staticmethod
    def v2(tp, jitter=0.0):
        return (core.T_OPT, corr.tree_player_params(jitter), tp.engine_tables())

    @staticmethod
    def param(P):
        return (core.T_PARAM, P, O.dummy_plan_arrays())

    def opponent(self, key, app):
        """app: the strategy that Sharp B mirrors / near-mirror jitters."""
        if key == "sharp_b":
            return app
        if key == "near_mirror":
            t, P, tabs = app
            P2 = P.copy(); P2[12] = 0.30
            return (t, P2, tabs)
        if key == "sharp_c":
            return (core.T_OPT, JITTER_P, self.sc)
        return self.param(self.s.profile(key).as_params())

    def run(self, me, opp_key, app, n, seed):
        """me, app = strategies. Returns (summary, hist_me, hist_opp)."""
        tA, PA, tabA = me
        tB, PB, tabB = self.opponent(opp_key, app)
        T = self.T
        wtl, hA, hB = core.simulate(n, seed, O.NCHUNK, tA, PA, tB, PB, T.R, T.D, T.act2, T.actN,
                                    T.splt, T.subd, *tabA, O.NV, *tabB)
        w, t, l = wtl.sum(axis=0)
        return summarize(int(w), int(t), int(l)), hA, hB


def me_players():
    """Parameter vectors for the non-plan players."""
    return {
        "basic_min": Profile("min", bets=[10]).as_params(),
        "basic_flat200": Profile("f200", bets=[200]).as_params(),
    }


def sweep_mix(x, kind):
    if kind == "nm":   # DP sees near-mirror players as "sharp_b" (same marginal distribution)
        return {"sharp_a": 0.0, "sharp_b": x, "casual_a": (1 - x) / 2, "casual_b": (1 - x) / 2,
                "sharp_c": 0.0}
    if kind == "ab":
        return {"sharp_a": x / 2, "sharp_b": x / 2, "casual_a": (1 - x) / 2, "casual_b": (1 - x) / 2,
                "sharp_c": 0.0}
    return {"sharp_a": 0.0, "sharp_b": 0.0, "casual_a": (1 - x) / 2, "casual_b": (1 - x) / 2,
            "sharp_c": x}


def breakeven_x(xs, rates, lows):
    def cross(vals):
        for i in range(len(xs) - 1):
            if vals[i] >= BREAKEVEN > vals[i + 1]:
                f = (vals[i] - BREAKEVEN) / (vals[i] - vals[i + 1])
                return xs[i] + f * (xs[i + 1] - xs[i])
        if vals[0] < BREAKEVEN:
            return 0.0
        return None    # never crosses: profitable at every mix tested
    return cross(rates), cross(lows)


# ----------------------------------------------------------------------------
# risk of ruin
# ----------------------------------------------------------------------------
def risk_of_ruin(W, T, L, bankroll=500.0, horizon=2000, paths=20000, seed=1):
    rng = np.random.default_rng(seed)
    out = {}
    for e, payout in ENTRIES.items():
        bank = np.full(paths, bankroll)
        alive = np.ones(paths, bool)
        ruined_at = np.full(paths, -1)
        for m in range(horizon):
            u = rng.random(paths)
            delta = np.where(u < W, payout - e, np.where(u < W + T, 0.0, -e))
            bank = np.where(alive, bank + delta, bank)
            newly = alive & (bank < e)
            ruined_at[newly] = m
            alive &= ~newly
        out[str(e)] = {"p_ruin": float((~alive).mean()),
                       "p_ruin_200": float(((ruined_at >= 0) & (ruined_at < 200)).mean()),
                       "median_bankroll": float(np.median(bank)),
                       "p5_bankroll": float(np.percentile(bank, 5)),
                       "ev_per_match": (0.8 * W - L) * e}
    return out


# ----------------------------------------------------------------------------
def house_edge_check(ctx: Ctx, n=10_000_000):
    P = np.zeros(20); P[0] = 10; P[6] = 1; P[11] = 1; P[12] = 5; P[13] = 5; P[19] = 1e6
    T = ctx.T
    j = core.sample_hands(n, 99, O.NCHUNK, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd,
                          np.zeros((1, 1)), np.zeros((6, 4)))
    p = j / j.sum()
    units = (np.arange(21) - 10) / 2.0
    m = p.sum(axis=(1, 2))
    ev = float((m * units).sum())
    sd = float(math.sqrt((m * units ** 2).sum() - ev ** 2))
    pp = p.sum(axis=(0, 2)); fc = p.sum(axis=(0, 1))
    return {"basic_ev_per_hand": ev, "basic_ev_se": sd / math.sqrt(n),
            "pp_sim_ev": float((pp * core.PP_MULT).sum()),
            "fc_sim_ev": float((fc * core.FC_MULT).sum()),
            "pp_exact": perfect_pairs_exact(), "fc_exact": four_card_total_exact(), "n": n}


OPP_KEYS = MODEL_KEYS + ["near_mirror"]


def run_all(n_main=10_000_000, n_sweep=2_000_000, quick=False):
    t0 = time.time()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    settings = Settings()
    log = lambda *a: print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)
    log("building tables, opponent distributions, plans ...")
    ctx = Ctx(settings, n_scen=500_000 if quick else 3_000_000)
    plan = ctx.plan_for(settings.mix)
    tp = ctx.tree_for(settings.mix)
    v2, v1 = ctx.v2(tp), ctx.v1(plan)
    rep = {"settings": json.loads(settings.to_json()), "n_main": n_main, "n_sweep": n_sweep,
           "breakeven": BREAKEVEN, "model_names": {**MODEL_NAMES, "near_mirror": "Near-mirror (this plan, bets +/-30%)"}}
    rep["house_edge"] = house_edge_check(ctx, 2_000_000 if quick else 20_000_000)
    log("house edge", rep["house_edge"]["basic_ev_per_hand"])

    # ---------- main matchups ----------
    players = {"optimizer": (v2, v2), "optimizer_v1": (v1, v1),
               "basic_min": (ctx.param(me_players()["basic_min"]), v2),
               "basic_flat200": (ctx.param(me_players()["basic_flat200"]), v2)}
    main, hists, seed = {}, {}, SEED
    for pname, (me, app) in players.items():
        main[pname] = {}
        for k in OPP_KEYS:
            if k == "near_mirror" and pname.startswith("basic"):
                continue
            seed += 1
            res, hA, hB = ctx.run(me, k, app, n_main, seed)
            main[pname][k] = res
            if pname == "optimizer":
                hists[f"me_vs_{k}"] = hA
                hists[f"opp_{k}"] = hB
            log(f"{pname:14s} vs {k:11s} W {res['win']:.4f} T {res['tie']:.4f} L {res['loss']:.4f} "
                f"dec {res['dec_rate']:.4f} [{res['dec_ci99'][0]:.4f},{res['dec_ci99'][1]:.4f}]")
        main[pname]["_default_mix"] = mixture(main[pname], settings.mix)
    rep["main"] = main
    rep["near_mirror"] = main["optimizer"]["near_mirror"]
    np.savez_compressed(os.path.join(RESULTS_DIR, "sim_hist.npz"), **hists)

    # ---------- sweeps (re-optimized for each mix) ----------
    xs = [i / 10 for i in range(11)]
    rep["sweeps"] = {}
    for kind in ("ab", "c", "nm"):
        rows = []
        for x in xs:
            mix = sweep_mix(x, kind)
            app = ctx.v2(ctx.tree_for(mix))
            per = {}
            for k in MODEL_KEYS:
                if mix.get(k, 0) <= 0:
                    continue
                seed += 1
                ek = "near_mirror" if (kind == "nm" and k == "sharp_b") else k
                per[k], _, _ = ctx.run(app, ek, app, n_sweep, seed)
            m = mixture(per, mix)
            fixed = mixture(main["optimizer"], mix) if kind == "ab" else None
            base = mixture(main["basic_min"], mix) if kind == "ab" else None
            rows.append({"x": x, "mix": mix, "reopt": m, "per_model": per,
                         "fixed_default_plan": fixed, "basic_min": base})
            log(f"sweep {kind} x={x:.1f} dec {m['dec_rate']:.4f} lo {m['dec_ci99'][0]:.4f} "
                f"ev {m['ev_per_dollar']:+.4f}")
        be, be_lo = breakeven_x(xs, [r["reopt"]["dec_rate"] for r in rows],
                                [r["reopt"]["dec_ci99"][0] for r in rows])
        rep["sweeps"][kind] = {"rows": rows, "breakeven_point": be, "breakeven_ci_low": be_lo}
        log(f"sweep {kind}: breakeven sharp% point={be} ci_low={be_lo}")
        if quick:
            break

    # ---------- sensitivity: plan optimized for mix X, played vs model Y ----------
    sens = {}
    cands = {"default": settings.mix,
             "all_casual": sweep_mix(0.0, "ab"), "50%_sharp": sweep_mix(0.5, "ab"),
             "only_sharp_a": {"sharp_a": 1.0}, "only_casual_a": {"casual_a": 1.0},
             "only_casual_b": {"casual_b": 1.0}, "with_25%_sharp_c": {**settings.mix, "sharp_c": 0.25}}
    if quick:
        cands = {"default": settings.mix, "only_casual_b": {"casual_b": 1.0}}
    for name, mix in cands.items():
        app = v2 if name == "default" else ctx.v2(ctx.tree_for(mix))
        sens[name] = {}
        for k in ("sharp_a", "casual_a", "casual_b", "sharp_c", "near_mirror"):
            seed += 1
            sens[name][k], _, _ = ctx.run(app, k, app, n_sweep, seed)
        sens[name]["_default_mix"] = mixture(sens[name], {**settings.mix, "sharp_b": 0.0})
        log(f"sensitivity {name:16s} " + " ".join(f"{k}:{v['dec_rate']:.3f}" for k, v in sens[name].items()))
    rep["sensitivity"] = sens

    # ---------- rule assumptions ----------
    rep["assumptions"] = {}
    variants = {"no_peek": {"dealer_peeks": False},
                "dealer_draws_if_all_bust": {"dealer_draws_if_all_bust": True},
                "split_by_value": {"split_by_value": True}}
    if quick:
        variants = {"no_peek": {"dealer_peeks": False}}
    for vname, flags in variants.items():
        s2 = Settings()
        s2.rules = Rules(**{**Rules().__dict__, **flags})
        c2 = Ctx(s2, n_scen=ctx.n_scen)
        app = c2.v2(c2.tree_for(s2.mix))
        per = {}
        for k in MODEL_KEYS:
            seed += 1
            per[k], _, _ = c2.run(app, k, app, n_sweep, seed)
        he = house_edge_check(c2, 2_000_000 if quick else 10_000_000)
        rep["assumptions"][vname] = {"per_model": per, "default_mix": mixture(per, s2.mix),
                                     "basic_ev_per_hand": he["basic_ev_per_hand"]}
        log(f"assumption {vname}: dec {rep['assumptions'][vname]['default_mix']['dec_rate']:.4f}")

    # ---------- bankroll ----------
    dm = main["optimizer"]["_default_mix"]
    rep["ruin_default_mix"] = risk_of_ruin(dm["win"], dm["tie"], dm["loss"])
    nm_rows = rep["sweeps"].get("nm", {}).get("rows", [])
    stress = nm_rows[5]["reopt"] if len(nm_rows) > 5 else dm
    rep["stress_mix"] = stress
    rep["ruin_stress_mix"] = risk_of_ruin(stress["win"], stress["tie"], stress["loss"])
    rep["elapsed_s"] = time.time() - t0
    with open(os.path.join(RESULTS_DIR, "report.json"), "w") as f:
        json.dump(rep, f, indent=1, default=float)
    from .report import write_markdown
    write_markdown(rep)
    log("done")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--n", type=int, default=10_000_000)
    ap.add_argument("--sweep-n", type=int, default=2_000_000)
    a = ap.parse_args()
    if a.quick:
        run_all(n_main=300_000, n_sweep=200_000, quick=True)
    else:
        run_all(n_main=a.n, n_sweep=a.sweep_n)
