"""
Match optimizer.

Goal: maximize the match objective, not expected chips.
  objective "money"   : U(x) = 0.8 * P(opp < x) - 1.0 * P(opp > x)   (ties refund -> 0)
                        = expected profit per $1 entry. This is what pays the bills.
  objective "winprob" : U(x) = P(opp < x)

Method
------
1. Simulate each opponent model alone -> distribution of its final chips.
   Mix them with the population weights -> F(opp final).
   Sharp B (mirror) uses OUR final distribution, solved by fixed-point iteration.
2. Terminal value V5(x) = U(x).
3. Backward DP over hands 5..1 on a 2.5-chip grid: at each chip level choose
   (main bet, Perfect Pairs stake, 4-Card-Total stake) maximizing E[V_{h+1}],
   using the simulated joint distribution of (main result, PP result, 4CT result)
   for one hand of basic strategy.
4. During the hand, every hit/stand/double/split/insurance decision is made by
   expectimax against V_{h+1} (core.play_hand / advisor), so play can deviate
   from basic strategy when the match situation calls for it.

KNOWN APPROXIMATION (important, see README): the opponent's final score is
treated as independent of our cards.  In the real game both players see the
SAME cards, so outcomes are correlated.  The validation simulation (validate.py)
models the shared shoe exactly, so the reported win rates are honest even
though the optimizer's internal estimates are not.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np

from . import core
from .config import Settings, MODEL_KEYS, RESULTS_DIR, CHIP_STEP
from .strategy import build_tables, Tables

NV = 40001          # value grid: 0 .. 100,000 chips
NCOMP = 4001        # DP solved exactly up to 10,000 chips; above that: min bet
NCHUNK = 64
from .config import CACHE_DIR  # noqa: E402


@dataclass
class Plan:
    key: str
    Vall: np.ndarray   # [6, NV] value before hand h (h=0..4), V[5] = terminal utility
    Wall: np.ndarray   # [6, NV] P(win) under the plan (independence model)
    Lall: np.ndarray   # [6, NV] P(loss)
    bet: np.ndarray    # [5, NCOMP]
    pp: np.ndarray     # [5, NCOMP]
    fc: np.ndarray     # [5, NCOMP]
    opp_pmf: np.ndarray  # [NV] mixed opponent final-chip pmf used
    model_pmfs: np.ndarray  # [4, NV] per-model opponent final pmf (sharp_b = our own)

    def save(self, path):
        np.savez_compressed(path, key=self.key, Vall=self.Vall, Wall=self.Wall, Lall=self.Lall,
                            bet=self.bet, pp=self.pp, fc=self.fc, opp_pmf=self.opp_pmf,
                            model_pmfs=self.model_pmfs)

    @staticmethod
    def load(path):
        z = np.load(path)
        return Plan(str(z["key"]), z["Vall"], z["Wall"], z["Lall"], z["bet"], z["pp"], z["fc"],
                    z["opp_pmf"], z["model_pmfs"])


def dummy_plan_arrays():
    return np.zeros((5, 1)), np.zeros((5, 1)), np.zeros((5, 1)), np.zeros((6, 4))


# ----------------------------------------------------------------------------
def joint_tables(T: Tables, n=4_000_000, seed=11):
    """Joint (main units, PP mult, FC mult, prob) for one basic-strategy hand,
    with doubles/splits affordable (full) and not affordable (nx)."""
    out = {}
    for name, chips in (("full", 1e6), ("nx", 25.0)):
        P = np.zeros(20)
        P[0] = 10; P[6] = 1; P[11] = 1; P[12] = 5; P[13] = 5; P[19] = chips
        d = np.zeros((1, 1))
        j = core.sample_hands(n, seed, NCHUNK, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd,
                              d, np.zeros((6, 4)))
        p = j / j.sum()
        idx = np.argwhere(p > 0)
        jm = (idx[:, 0] - 10) / 2.0
        jp = core.PP_MULT[idx[:, 1]]
        jf = core.FC_MULT[idx[:, 2]]
        jw = p[p > 0]
        out[name] = (jm.astype(np.float64), jp.astype(np.float64), jf.astype(np.float64),
                     jw.astype(np.float64))
    return out


def simulate_alone(T: Tables, ptype, P, n, seed, plan_arrays=None):
    """Final chip pmf of one player type (it plays a dummy match vs itself)."""
    bet, pp, fc, V = plan_arrays if plan_arrays is not None else dummy_plan_arrays()
    _, hA, _ = core.simulate(n, seed, NCHUNK, ptype, P, core.T_PARAM, core.ZP, T.R, T.D,
                             T.act2, T.actN, T.splt, T.subd, bet, pp, fc, V, NV,
                             bet, pp, fc, V)
    return hA / hA.sum()


def terminal_utility(pmf, objective):
    cdf = np.cumsum(pmf)
    less = np.concatenate([[0.0], cdf[:-1]])        # P(opp < x)
    greater = 1.0 - cdf                              # P(opp > x)
    if objective == "winprob":
        U = less.copy()
    else:
        U = 0.8 * less - greater
    return U, less, greater


def solve_dp(T: Tables, J, opp_pmf, settings: Settings):
    U, W, L = terminal_utility(opp_pmf, settings.objective)
    Vall = np.zeros((6, NV)); Wall = np.zeros((6, NV)); Lall = np.zeros((6, NV))
    Vall[5], Wall[5], Lall[5] = U, W, L
    bet = np.zeros((5, NCOMP)); pp = np.zeros((5, NCOMP)); fc = np.zeros((5, NCOMP))
    r = settings.rules
    jf_, jn_ = J["full"], J["nx"]
    for h in range(4, -1, -1):
        V, Wv, Lv, bt, pt, ft = core.dp_step(Vall[h + 1], Wall[h + 1], Lall[h + 1], NCOMP,
                                              *jf_, *jn_, r.min_bet, r.side_min, r.side_max_frac)
        Vall[h], Wall[h], Lall[h] = V, Wv, Lv
        bet[h], pp[h], fc[h] = bt, pt, ft
    return Vall, Wall, Lall, bet, pp, fc


def sharp_c_plan(settings: Settings, T: Tables, J, sharp_a_pmf):
    """Sharp C's strategy: the same machinery, but believing every opponent is a
    flat-betting Sharp A and maximizing plain P(win)."""
    s2 = Settings.from_dict({"rules": settings.rules.__dict__, "objective": "winprob"})
    Vall, Wall, Lall, bet, pp, fc = solve_dp(T, J, sharp_a_pmf, s2)
    return bet, pp, fc, Vall


def model_pmfs_for(settings: Settings, T: Tables, J, n_opp=1_000_000, seed=7):
    """Final-chip pmf for each model except sharp_b (which depends on our plan)."""
    pm = np.zeros((len(MODEL_KEYS), NV))
    for i, k in enumerate(MODEL_KEYS):
        if k in ("sharp_b", "sharp_c"):
            continue
        pm[i] = simulate_alone(T, core.T_PARAM, settings.profile(k).as_params(), n_opp, seed + i)
    ia, ic = MODEL_KEYS.index("sharp_a"), MODEL_KEYS.index("sharp_c")
    jp = core.ZP.copy(); jp[12] = 0.30
    pm[ic] = simulate_alone(T, core.T_OPT, jp, n_opp, seed + 50,
                            sharp_c_plan(settings, T, J, pm[ia]))
    return pm


def build_plan(settings: Settings, n_opp=1_000_000, seed=7, iters=2, verbose=True,
               T: Tables | None = None, J=None, model_pmfs=None) -> Plan:
    t0 = time.time()
    T = T or build_tables(settings.rules)
    J = J or joint_tables(T)
    if model_pmfs is None:
        model_pmfs = model_pmfs_for(settings, T, J, n_opp, seed)
    else:
        model_pmfs = model_pmfs.copy()
    w = np.array([settings.mix.get(k, 0.0) for k in MODEL_KEYS], dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.ones(len(MODEL_KEYS)) / len(MODEL_KEYS)
    ib = MODEL_KEYS.index("sharp_b")
    # mirror model: start from Sharp A's distribution, then iterate to our own
    model_pmfs[ib] = model_pmfs[MODEL_KEYS.index("sharp_a")]
    plan = None
    for it in range(iters if w[ib] > 0 else 1):
        mix = (w[:, None] * model_pmfs).sum(axis=0)
        Vall, Wall, Lall, bet, pp, fc = solve_dp(T, J, mix, settings)
        plan = Plan(settings.key(), Vall, Wall, Lall, bet, pp, fc, mix, model_pmfs.copy())
        if w[ib] > 0 or it == 0:
            model_pmfs[ib] = simulate_alone(T, core.T_OPT, core.ZP, n_opp, seed + 99 + it,
                                            (bet, pp, fc, Vall))
    plan.model_pmfs = model_pmfs
    if verbose:
        print(f"  plan built in {time.time() - t0:.1f}s  (model est. P(win) {plan.Wall[0][400]:.3f}, "
              f"P(loss) {plan.Lall[0][400]:.3f})")
    return plan


def get_plan(settings: Settings, verbose=True) -> Plan:
    """Cached plan for these settings (recomputed if settings changed)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"plan_{settings.key()}.npz")
    if os.path.exists(path):
        return Plan.load(path)
    plan = build_plan(settings, verbose=verbose)
    plan.save(path)
    return plan
