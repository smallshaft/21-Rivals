"""
Robustness: play the DEFAULT plan against opponents whose habits differ from the
profiles it was optimized against.  If the edge only exists against the exact
assumed opponents, it's overfit.

    python -m rivals.robustness      (appends to results/report.json and REPORT.md)
"""
from __future__ import annotations

import json
import os

from . import core
from .config import Settings, Profile, RESULTS_DIR
from .validate import Ctx, summarize, me_players
from . import optimizer as O

VARIANTS = {
    "casual_a_other_bets": Profile("Casual A, bets 20/40/75/125/175, fewer mistakes",
                                   bets=[20, 40, 75, 125, 175], bet_per_match=False, p_insurance=0.3,
                                   p_stand_stiff=0.25, p_skip_double=0.2, p_skip_split=0.2, p_side=0.2,
                                   side_min=5, side_max=25, p_error=0.04),
    "casual_a_big_bets": Profile("Casual A, bets 100-500",
                                 bets=[100, 200, 300, 400, 500], bet_per_match=False, p_insurance=0.6,
                                 p_stand_stiff=0.45, p_skip_double=0.35, p_skip_split=0.35, p_side=0.35,
                                 side_min=5, side_max=25, p_error=0.08),
    "casual_b_one_shove": Profile("Degen, exactly one all-in, small sides",
                                  bets=[25, 50, 100], bet_per_match=False, p_insurance=0.35,
                                  p_side=0.5, side_min=5, side_max=25, allin_hands=1.0, p_error=0.05),
    "sharp_min_bets": Profile("Sharp, basic strategy, bets 10-30 flat", bets=[10, 15, 20, 30]),
    "sharp_big_flat": Profile("Sharp, basic strategy, flat 300-500", bets=[300, 400, 500]),
    "sharp_odd_flat": Profile("Sharp, basic strategy, flat 35/65/135/240", bets=[35, 65, 135, 240]),
}


def run(n=2_000_000, seed=777):
    s = Settings()
    ctx = Ctx(s)
    v2 = ctx.v2(ctx.tree_for(s.mix))
    v1 = ctx.v1(ctx.plan_for(s.mix))
    base = ctx.param(me_players()["basic_min"])
    T = ctx.T
    out = {}
    for k, prof in VARIANTS.items():
        res = {}
        for name, (tA, PA, tabA) in (("optimizer", v2), ("optimizer_v1", v1), ("basic_min", base)):
            seed += 1
            wtl, _, _ = core.simulate(n, seed, O.NCHUNK, tA, PA, core.T_PARAM, prof.as_params(),
                                      T.R, T.D, T.act2, T.actN, T.splt, T.subd, *tabA, O.NV,
                                      *O.dummy_plan_arrays())
            w, t, l = wtl.sum(axis=0)
            res[name] = summarize(int(w), int(t), int(l))
        res["name"] = prof.name
        out[k] = res
        print(f"{prof.name:50s} v2 {res['optimizer']['dec_rate']:.4f}  v1 {res['optimizer_v1']['dec_rate']:.4f}"
              f"  basic_min {res['basic_min']['dec_rate']:.4f}")
    path = os.path.join(RESULTS_DIR, "report.json")
    with open(path) as f:
        rep = json.load(f)
    rep["robustness"] = out
    with open(path, "w") as f:
        json.dump(rep, f, indent=1, default=float)
    from .report import write_markdown
    write_markdown(rep)
    return out


if __name__ == "__main__":
    run()
