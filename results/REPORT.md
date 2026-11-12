# 21 Rivals - simulation report

Matches per main matchup: **10,000,000**, per sweep/sensitivity cell: 2,000,000. Fixed seeds. Break-even = 55.56% of decided matches (ties refund).

## Engine checks

- Basic strategy EV per hand (sim, 20,000,000 hands): **-0.547%** (+/- 0.065% at 99%). Published 6-deck S17 DAS no-surrender is about -0.40% to -0.45% with full doubling; restricting doubles to 9-11 and one split costs about another 0.10-0.15%, so ~-0.55% is expected.
- Perfect Pairs: exact EV -6.109% (-19/311), sim -5.973%
- 4-Card Total: exact EV -4.487%, sim -4.539%

## Head-to-head results (exact shared-shoe simulation)

### Optimizer (this app)

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 66.36% | 0.01% | 33.63% | 66.37% | [66.33, 66.40] | +0.1946 | +0.195 | +0.973 | +1.946 | +3.891 |
| Sharp B (mirror: same optimizer) | 0.00% | 100.00% | 0.00% | nan% | [nan, nan] | +0.0000 | +0.000 | +0.000 | +0.000 | +0.000 |
| Casual A (gut feel) | 61.96% | 0.25% | 37.78% | 62.12% | [62.08, 62.16] | +0.1179 | +0.118 | +0.589 | +1.179 | +2.357 |
| Casual B (degen) | 67.93% | 0.06% | 32.01% | 67.97% | [67.93, 68.01] | +0.2234 | +0.223 | +1.117 | +2.234 | +4.467 |
| Sharp C (match-aware, own model) | 77.90% | 1.74% | 20.36% | 79.28% | [79.24, 79.31] | +0.4195 | +0.420 | +2.098 | +4.195 | +8.391 |
| **Default mix** | 57.00% | 12.62% | 30.38% | 65.24% | [65.21, 65.26] | +0.1523 | +0.152 | +0.761 | +1.523 | +3.046 |

Default-mix verdict: **PROFITABLE (99% CI above 55.56%)**

### Baseline: basic strategy + 10 bets

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 45.70% | 11.06% | 43.24% | 51.38% | [51.34, 51.43] | -0.0668 | -0.067 | -0.334 | -0.668 | -1.336 |
| Sharp B (mirror: same optimizer) | 26.90% | 0.00% | 73.10% | 26.90% | [26.86, 26.94] | -0.5158 | -0.516 | -2.579 | -5.158 | -10.316 |
| Casual A (gut feel) | 53.93% | 0.61% | 45.46% | 54.26% | [54.22, 54.30] | -0.0232 | -0.023 | -0.116 | -0.232 | -0.464 |
| Casual B (degen) | 67.34% | 0.06% | 32.61% | 67.38% | [67.34, 67.41] | +0.2127 | +0.213 | +1.063 | +2.127 | +4.253 |
| Sharp C (match-aware, own model) | 18.61% | 0.02% | 81.37% | 18.62% | [18.59, 18.65] | -0.6648 | -0.665 | -3.324 | -6.648 | -13.295 |
| **Default mix** | 54.55% | 1.63% | 43.82% | 55.46% | [55.43, 55.48] | -0.0018 | -0.002 | -0.009 | -0.018 | -0.035 |

Default-mix verdict: **NOT profitable**

### Baseline: basic strategy + flat 200

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 32.42% | 33.30% | 34.27% | 48.61% | [48.56, 48.66] | -0.0834 | -0.083 | -0.417 | -0.834 | -1.668 |
| Sharp B (mirror: same optimizer) | 46.09% | 0.02% | 53.89% | 46.10% | [46.06, 46.14] | -0.1702 | -0.170 | -0.851 | -1.702 | -3.405 |
| Casual A (gut feel) | 51.23% | 0.50% | 48.27% | 51.49% | [51.45, 51.53] | -0.0729 | -0.073 | -0.364 | -0.729 | -1.457 |
| Casual B (degen) | 63.87% | 3.78% | 32.35% | 66.38% | [66.34, 66.42] | +0.1875 | +0.187 | +0.937 | +1.875 | +3.749 |
| Sharp C (match-aware, own model) | 47.32% | 2.65% | 50.03% | 48.61% | [48.57, 48.65] | -0.1217 | -0.122 | -0.609 | -1.217 | -2.434 |
| **Default mix** | 52.98% | 5.77% | 41.25% | 56.22% | [56.20, 56.24] | +0.0113 | +0.011 | +0.056 | +0.113 | +0.226 |

Default-mix verdict: **PROFITABLE (99% CI above 55.56%)**

### Attribution: optimizer bets, basic-strategy play

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 66.11% | 0.01% | 33.88% | 66.11% | [66.03, 66.20] | +0.1900 | +0.190 | +0.950 | +1.900 | +3.800 |
| Sharp B (mirror: same optimizer) | 15.71% | 72.41% | 11.88% | 56.93% | [56.76, 57.10] | +0.0068 | +0.007 | +0.034 | +0.068 | +0.136 |
| Casual A (gut feel) | 62.04% | 0.24% | 37.71% | 62.19% | [62.10, 62.28] | +0.1192 | +0.119 | +0.596 | +1.192 | +2.384 |
| Casual B (degen) | 67.94% | 0.07% | 31.99% | 67.99% | [67.90, 68.07] | +0.2236 | +0.224 | +1.118 | +2.236 | +4.473 |
| Sharp C (match-aware, own model) | 77.32% | 1.62% | 21.06% | 78.59% | [78.52, 78.67] | +0.4079 | +0.408 | +2.040 | +4.079 | +8.158 |
| **Default mix** | 58.97% | 9.17% | 31.86% | 64.92% | [64.87, 64.98] | +0.1532 | +0.153 | +0.766 | +1.532 | +3.063 |

Default-mix verdict: **PROFITABLE (99% CI above 55.56%)**

### Attribution: optimizer without side stakes

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 65.43% | 0.02% | 34.55% | 65.44% | [65.36, 65.53] | +0.1779 | +0.178 | +0.890 | +1.779 | +3.559 |
| Sharp B (mirror: same optimizer) | 42.98% | 52.17% | 4.85% | 89.85% | [89.77, 89.93] | +0.2953 | +0.295 | +1.476 | +2.953 | +5.905 |
| Casual A (gut feel) | 61.16% | 0.26% | 38.58% | 61.32% | [61.23, 61.41] | +0.1035 | +0.104 | +0.518 | +1.035 | +2.071 |
| Casual B (degen) | 67.82% | 0.05% | 32.13% | 67.86% | [67.77, 67.94] | +0.2213 | +0.221 | +1.106 | +2.213 | +4.426 |
| Sharp C (match-aware, own model) | 81.19% | 0.28% | 18.53% | 81.42% | [81.35, 81.49] | +0.4643 | +0.464 | +2.321 | +4.643 | +9.286 |
| **Default mix** | 61.92% | 6.64% | 31.44% | 66.32% | [66.27, 66.37] | +0.1810 | +0.181 | +0.905 | +1.810 | +3.619 |

Default-mix verdict: **PROFITABLE (99% CI above 55.56%)**

### Near-mirror stress test

Opponent runs this same plan but sizes every bet +/-30% (random per match): win 44.71%, tie 8.23%, loss 47.06%, **48.72% of decided** [48.63, 48.82] -> NOT profitable.

## Sharp-percentage sweeps (strategy re-optimized at every mix)

### Sharp = half Sharp A (flat basic) + half Sharp B (mirror)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 65.20% | [65.14, 65.26] | 0.15% | +0.1733 | 65.05% | 60.84% |
| 10% | 65.24% | [65.18, 65.30] | 5.14% | +0.1654 | 65.12% | 58.70% |
| 20% | 65.22% | [65.16, 65.27] | 10.13% | +0.1563 | 65.20% | 56.54% |
| 30% | 65.25% | [65.19, 65.30] | 15.11% | +0.1481 | 65.28% | 54.36% |
| 40% | 65.35% | [65.30, 65.40] | 20.10% | +0.1409 | 65.38% | 52.16% |
| 50% | 65.43% | [65.38, 65.48] | 25.08% | +0.1332 | 65.49% | 49.93% |
| 60% | 65.52% | [65.47, 65.57] | 30.07% | +0.1254 | 65.61% | 47.68% |
| 70% | 65.70% | [65.65, 65.75] | 35.05% | +0.1186 | 65.76% | 45.40% |
| 80% | 65.58% | [65.52, 65.65] | 40.04% | +0.1082 | 65.93% | 43.10% |
| 90% | 66.32% | [66.25, 66.39] | 45.03% | +0.1065 | 66.13% | 40.78% |
| 100% | 66.89% | [66.80, 66.97] | 50.01% | +0.1020 | 66.37% | 38.43% |

Break-even (point estimate): **never (profitable at every mix tested)**; break-even using the 99% CI lower bound: **never (profitable at every mix tested)**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

### STRESS: Sharp = Sharp C (match-aware player with its own model)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 65.17% | [65.11, 65.24] | 0.16% | +0.1729 | - | - |
| 10% | 66.38% | [66.32, 66.44] | 0.29% | +0.1943 | - | - |
| 20% | 67.83% | [67.78, 67.88] | 0.47% | +0.2200 | - | - |
| 30% | 69.29% | [69.24, 69.34] | 0.63% | +0.2457 | - | - |
| 40% | 70.67% | [70.62, 70.72] | 0.76% | +0.2700 | - | - |
| 50% | 72.89% | [72.84, 72.94] | 0.32% | +0.3111 | - | - |
| 60% | 74.71% | [74.66, 74.76] | 0.30% | +0.3438 | - | - |
| 70% | 77.60% | [77.55, 77.65] | 0.31% | +0.3956 | - | - |
| 80% | 79.52% | [79.46, 79.57] | 0.35% | +0.4298 | - | - |
| 90% | 81.36% | [81.30, 81.43] | 0.37% | +0.4628 | - | - |
| 100% | 83.24% | [83.17, 83.31] | 0.39% | +0.4963 | - | - |

Break-even (point estimate): **never (profitable at every mix tested)**; break-even using the 99% CI lower bound: **never (profitable at every mix tested)**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

### STRESS: Sharp = near-mirror (this same plan, bets +/-30%)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 65.20% | [65.14, 65.26] | 0.16% | +0.1734 | - | - |
| 10% | 63.48% | [63.42, 63.53] | 0.83% | +0.1414 | - | - |
| 20% | 60.71% | [60.66, 60.77] | 1.83% | +0.0912 | - | - |
| 30% | 58.21% | [58.16, 58.26] | 2.85% | +0.0464 | - | - |
| 40% | 56.31% | [56.26, 56.36] | 3.37% | +0.0131 | - | - |
| 50% | 53.53% | [53.47, 53.58] | 3.65% | -0.0352 | - | - |
| 60% | 52.46% | [52.40, 52.53] | 4.48% | -0.0531 | - | - |
| 70% | 49.96% | [49.90, 50.03] | 5.41% | -0.0952 | - | - |
| 80% | 50.31% | [50.23, 50.39] | 5.79% | -0.0890 | - | - |
| 90% | 53.25% | [53.16, 53.33] | 8.63% | -0.0380 | - | - |
| 100% | 51.26% | [51.16, 51.35] | 8.04% | -0.0711 | - | - |

Break-even (point estimate): **43% sharp**; break-even using the 99% CI lower bound: **43% sharp**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

## Sensitivity: strategy optimized for mix X, played against opponent Y (win% of decided)

| Optimized for | Sharp A (basic, flat bets) | Casual A (gut feel) | Casual B (degen) | Sharp C (match-aware, own model) | Default mix |
|---|---|---|---|---|---|
| default | 66.37% | 62.10% | 68.00% | 79.30% | 65.24% |
| all_casual | 65.73% | 62.16% | 68.16% | 77.33% | 65.24% |
| 50%_sharp | 66.34% | 61.98% | 67.86% | 79.46% | 65.12% |
| 100%_sharp_ab | 66.87% | 61.39% | 67.79% | 79.10% | 64.92% |
| only_sharp_a | 69.72% | 60.08% | 67.01% | 51.80% | 64.41% |
| only_casual_a | 67.77% | 61.94% | 61.65% | 74.84% | 62.72% |
| only_casual_b | 42.06% | 41.25% | 71.82% | 51.00% | 54.47% |

## Robustness: default plan vs opponents it was NOT tuned for

| Opponent variant | Optimizer win% decided | 99% CI | Basic+min bets |
|---|---|---|---|
| Casual A, bets 20/40/75/125/175, fewer mistakes | 64.70% | [64.61, 64.78] | 53.05% |
| Casual A, bets 100-500 | 56.51% | [56.41, 56.60] | 55.58% |
| Degen, exactly one all-in, small sides | 54.51% | [54.42, 54.60] | 53.21% |
| Sharp, basic strategy, bets 10-30 flat | 73.14% | [73.06, 73.22] | 51.30% |
| Sharp, basic strategy, flat 300-500 | 58.88% | [58.79, 58.97] | 55.59% |
| Sharp, basic strategy, flat 35/65/135/240 | 63.68% | [63.60, 63.77] | 51.44% |

## Rule assumptions (default mix, re-optimized)

| Variant | Win% decided | 99% CI | Basic EV/hand |
|---|---|---|---|
| Default rules | 65.24% | [65.21, 65.26] | -0.547% |
| no_peek | 65.32% | [65.27, 65.38] | -0.615% |
| dealer_draws_if_all_bust | 65.26% | [65.20, 65.31] | -0.512% |
| split_by_value | 65.22% | [65.17, 65.27] | -0.512% |

## Bankroll ($500), 2,000-match horizon

### Default mix

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | +0.152 | 0.0% | 0.0% | $804 | $746 |
| $5 | +0.761 | 0.0% | 0.0% | $2,021 | $1,723 |
| $10 | +1.523 | 0.0% | 0.0% | $3,550 | $2,952 |
| $20 | +3.046 | 0.0% | 0.0% | $6,596 | $5,420 |

### Stress mix (50% near-mirror players, 50% casuals)

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | -0.035 | 0.0% | 0.0% | $430 | $365 |
| $5 | -0.176 | 0.0% | 30.4% | $146 | $1 |
| $10 | -0.352 | 0.0% | 80.3% | $6 | $0 |
| $20 | -0.703 | 13.4% | 95.1% | $12 | $0 |

## Entry-size recommendation ($500 bankroll)

- Under the default mix, every entry size has under 1% simulated risk of ruin on $500 (largest passing: $20). Required bankroll for <1% ruin is about **10 entries** (diffusion approximation): $10 for $1, $49 for $5, $98 for $10, $195 for $20.
- **But the model's edge is unproven in the real pool.** Start at **$1** until the dashboard shows 200+ logged decided matches with the real 99% CI lower bound above 55.56%. Then move to $5. Move to $10 only with 400+ matches still above break-even and a bankroll of at least 100 entries ($1,000). Use $20 only above $2,000.
- Move down one level if bankroll drops below 50 entries of the current level, or if the real win rate's 99% CI upper bound drops below 55.56% (you're losing), or if the real rate sits far below the sim prediction (the model is wrong about the pool).
- Worst realistic case: if most opponents are near-mirror players, the win rate is 48.72% of decided matches. That loses money at every entry size.
