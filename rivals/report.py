"""Turns results/report.json into a readable results/REPORT.md."""
from __future__ import annotations

import json
import os

from .config import RESULTS_DIR, BREAKEVEN, MODEL_KEYS, MODEL_NAMES, ENTRIES


def pct(x, d=2):
    return f"{100 * x:.{d}f}%"


def ci(c, d=2):
    return f"[{100 * c[0]:.{d}f}, {100 * c[1]:.{d}f}]"


def verdict(r):
    lo = r["dec_ci99"][0]
    if lo > BREAKEVEN:
        return "PROFITABLE (99% CI above 55.56%)"
    if r["dec_rate"] > BREAKEVEN:
        return "point estimate above break-even, CI not conclusive"
    return "NOT profitable"


def recommendation(rep: dict) -> str:
    """Largest entry whose risk of ruin over 2,000 matches is < 1% under the default mix.
    Move-up/down thresholds use the same 1% rule on the current bankroll."""
    dm = rep["main"]["optimizer"]["_default_mix"]
    if dm["dec_ci99"][0] <= BREAKEVEN:
        return ("The default-mix result is not above break-even with 99% confidence, so the honest "
                "recommendation is **don't play for money**, or play $1 only to collect real data.\n")
    ok = [int(e) for e, r in rep["ruin_default_mix"].items() if r["p_ruin"] < 0.01]
    best = max(ok) if ok else 1
    ev = dm["ev_per_dollar"]
    var = 0.64 * dm["win"] + dm["loss"] - ev ** 2
    # bankroll needed for <1% ruin (diffusion approximation): B = -ln(0.01) * var / (2 ev) entries
    need = (4.605 * var / (2 * ev)) if ev > 0 else float("inf")
    lines = [f"- Under the default mix, every entry size has under 1% simulated risk of ruin on $500 "
             f"(largest passing: ${best}). Required bankroll for <1% ruin is about **{need:.0f} entries** "
             f"(diffusion approximation): ${need:.0f} for $1, ${5 * need:.0f} for $5, ${10 * need:.0f} for $10, "
             f"${20 * need:.0f} for $20." if ok else "- No entry size passes the 1% ruin test."]
    lines.append("- **But the model's edge is unproven in the real pool.** Start at **$1** until the dashboard "
                 "shows 200+ logged decided matches with the real 99% CI lower bound above 55.56%. "
                 "Then move to $5. Move to $10 only with 400+ matches still above break-even and a bankroll of at "
                 "least 100 entries ($1,000). Use $20 only above $2,000.")
    lines.append("- Move down one level if bankroll drops below 50 entries of the current level, or if the "
                 "real win rate's 99% CI upper bound drops below 55.56% (you're losing), or if the real rate "
                 "sits far below the sim prediction (the model is wrong about the pool).")
    nm = rep.get("near_mirror")
    if nm:
        lines.append(f"- Worst realistic case: if most opponents are near-mirror players, the win rate is "
                     f"{pct(nm['dec_rate'])} of decided matches. That loses money at every entry size.")
    return "\n".join(lines) + "\n"


def write_markdown(rep: dict, path=None):
    path = path or os.path.join(RESULTS_DIR, "REPORT.md")
    L = []
    w = L.append
    w("# 21 Rivals - simulation report\n")
    w(f"Matches per main matchup: **{rep['n_main']:,}**, per sweep/sensitivity cell: {rep['n_sweep']:,}. "
      f"Fixed seeds. Break-even = {pct(BREAKEVEN)} of decided matches (ties refund).\n")
    he = rep["house_edge"]
    w("## Engine checks\n")
    w(f"- Basic strategy EV per hand (sim, {he['n']:,} hands): **{pct(he['basic_ev_per_hand'], 3)}** "
      f"(+/- {pct(Z := 2.576 * he['basic_ev_se'], 3)} at 99%). Published 6-deck S17 DAS no-surrender "
      f"is about -0.40% to -0.45% with full doubling; restricting doubles to 9-11 and one split "
      f"costs about another 0.10-0.15%, so ~-0.55% is expected.")
    w(f"- Perfect Pairs: exact EV {pct(he['pp_exact']['ev'], 3)} ({he['pp_exact']['ev_exact']}), "
      f"sim {pct(he['pp_sim_ev'], 3)}")
    w(f"- 4-Card Total: exact EV {pct(he['fc_exact']['ev'], 3)}, sim {pct(he['fc_sim_ev'], 3)}\n")

    w("## Head-to-head results (exact shared-shoe simulation)\n")
    for pname, label in (("optimizer", "Optimizer (this app)"), ("basic_min", "Baseline: basic strategy + 10 bets"),
                         ("basic_flat200", "Baseline: basic strategy + flat 200"),
                         ("opt_basic_play", "Attribution: optimizer bets, basic-strategy play"),
                         ("opt_no_sides", "Attribution: optimizer without side stakes")):
        res = rep["main"][pname]
        w(f"### {label}\n")
        w("| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for k in MODEL_KEYS + ["_default_mix"]:
            r = res[k]
            name = "**Default mix**" if k == "_default_mix" else MODEL_NAMES[k]
            pm = r["profit_per_match"]
            w(f"| {name} | {pct(r['win'])} | {pct(r['tie'])} | {pct(r['loss'])} | {pct(r['dec_rate'])} | "
              f"{ci(r['dec_ci99'])} | {r['ev_per_dollar']:+.4f} | "
              + " | ".join(f"{pm[str(e)]:+.3f}" for e in ENTRIES) + " |")
        w(f"\nDefault-mix verdict: **{verdict(res['_default_mix'])}**\n")

    nm = rep.get("near_mirror")
    if nm:
        w("### Near-mirror stress test\n")
        w(f"Opponent runs this same plan but sizes every bet +/-30% (random per match): "
          f"win {pct(nm['win'])}, tie {pct(nm['tie'])}, loss {pct(nm['loss'])}, "
          f"**{pct(nm['dec_rate'])} of decided** {ci(nm['dec_ci99'])} -> {verdict(nm)}.\n")

    w("## Sharp-percentage sweeps (strategy re-optimized at every mix)\n")
    for kind, title in (("ab", "Sharp = half Sharp A (flat basic) + half Sharp B (mirror)"),
                        ("c", "STRESS: Sharp = Sharp C (match-aware player with its own model)"),
                        ("nm", "STRESS: Sharp = near-mirror (this same plan, bets +/-30%)")):
        if kind not in rep["sweeps"]:
            continue
        sw = rep["sweeps"][kind]
        w(f"### {title}\n")
        w("| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |")
        w("|---|---|---|---|---|---|---|")
        for r in sw["rows"]:
            m = r["reopt"]
            fx = f"{pct(r['fixed_default_plan']['dec_rate'])}" if r.get("fixed_default_plan") else "-"
            bm = f"{pct(r['basic_min']['dec_rate'])}" if r.get("basic_min") else "-"
            w(f"| {int(round(100 * r['x']))}% | {pct(m['dec_rate'])} | {ci(m['dec_ci99'])} | {pct(m['tie'])} | "
              f"{m['ev_per_dollar']:+.4f} | {fx} | {bm} |")
        be, lo = sw["breakeven_point"], sw["breakeven_ci_low"]
        f = lambda v: "never (profitable at every mix tested)" if v is None else f"{100 * v:.0f}% sharp"
        w(f"\nBreak-even (point estimate): **{f(be)}**; break-even using the 99% CI lower bound: **{f(lo)}**. "
          "Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.\n")

    w("## Sensitivity: strategy optimized for mix X, played against opponent Y (win% of decided)\n")
    sens = rep["sensitivity"]
    cols = ["sharp_a", "casual_a", "casual_b", "sharp_c", "_default_mix"]
    w("| Optimized for | " + " | ".join("Default mix" if c == "_default_mix" else MODEL_NAMES[c] for c in cols) + " |")
    w("|---" * (len(cols) + 1) + "|")
    for name, row in sens.items():
        w(f"| {name} | " + " | ".join(pct(row[c]['dec_rate']) for c in cols) + " |")
    w("")

    rob = rep.get("robustness")
    if rob:
        w("## Robustness: default plan vs opponents it was NOT tuned for\n")
        w("| Opponent variant | Optimizer win% decided | 99% CI | Basic+min bets |")
        w("|---|---|---|---|")
        for k, v in rob.items():
            o = v["optimizer"]
            w(f"| {v['name']} | {pct(o['dec_rate'])} | {ci(o['dec_ci99'])} | {pct(v['basic_min']['dec_rate'])} |")
        w("")

    w("## Rule assumptions (default mix, re-optimized)\n")
    w("| Variant | Win% decided | 99% CI | Basic EV/hand |")
    w("|---|---|---|---|")
    w(f"| Default rules | {pct(rep['main']['optimizer']['_default_mix']['dec_rate'])} | "
      f"{ci(rep['main']['optimizer']['_default_mix']['dec_ci99'])} | {pct(he['basic_ev_per_hand'], 3)} |")
    for k, v in rep["assumptions"].items():
        m = v["default_mix"]
        w(f"| {k} | {pct(m['dec_rate'])} | {ci(m['dec_ci99'])} | {pct(v['basic_ev_per_hand'], 3)} |")
    w("")

    w("## Bankroll ($500), 2,000-match horizon\n")
    for key, title in (("ruin_default_mix", "Default mix"), ("ruin_stress_mix", "Stress mix (50% near-mirror players, 50% casuals)")):
        w(f"### {title}\n")
        w("| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |")
        w("|---|---|---|---|---|---|")
        for e, r in rep[key].items():
            w(f"| ${e} | {r['ev_per_match']:+.3f} | {pct(r['p_ruin_200'], 1)} | {pct(r['p_ruin'], 1)} | "
              f"${r['median_bankroll']:,.0f} | ${r['p5_bankroll']:,.0f} |")
        w("")
    w("## Entry-size recommendation ($500 bankroll)\n")
    w(recommendation(rep))
    with open(path, "w") as f:
        f.write("\n".join(L))
    return path


if __name__ == "__main__":
    with open(os.path.join(RESULTS_DIR, "report.json")) as f:
        write_markdown(json.load(f))
