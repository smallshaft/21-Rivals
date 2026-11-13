# 21 Rivals - simulation report

Matches per main matchup: **10,000,000**, per sweep/sensitivity cell: 2,000,000. Fixed seeds. Break-even = 55.56% of decided matches (ties refund).

## Engine checks

- Basic strategy EV per hand (sim, 20,000,000 hands): **-0.547%** (+/- 0.065% at 99%). Published 6-deck S17 DAS no-surrender is about -0.40% to -0.45% with full doubling; restricting doubles to 9-11 and one split costs about another 0.10-0.15%, so ~-0.55% is expected.
- Perfect Pairs: exact EV -6.109% (-19/311), sim -5.973%
- 4-Card Total: exact EV -4.487%, sim -4.539%

## Head-to-head results (exact shared-shoe simulation)

### v2 optimizer: prices in the shared cards (this app)

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 73.15% | 0.17% | 26.68% | 73.28% | [73.24, 73.31] | +0.3184 | +0.318 | +1.592 | +3.184 | +6.368 |
| Sharp B (mirror: same optimizer) | 0.00% | 100.00% | 0.00% | nan% | [nan, nan] | +0.0000 | +0.000 | +0.000 | +0.000 | +0.000 |
| Casual A (gut feel) | 64.43% | 0.33% | 35.24% | 64.64% | [64.60, 64.68] | +0.1630 | +0.163 | +0.815 | +1.630 | +3.259 |
| Casual B (degen) | 68.36% | 0.08% | 31.56% | 68.41% | [68.38, 68.45] | +0.2313 | +0.231 | +1.156 | +2.313 | +4.625 |
| Sharp C (match-aware, own model) | 59.61% | 0.97% | 39.42% | 60.19% | [60.15, 60.23] | +0.0827 | +0.083 | +0.413 | +0.827 | +1.653 |
| Near-mirror (this plan, bets +/-30%) | 45.84% | 10.01% | 44.16% | 50.93% | [50.89, 50.98] | -0.0749 | -0.075 | -0.374 | -0.749 | -1.498 |
| **Default mix** | 58.94% | 12.68% | 28.39% | 67.49% | [67.47, 67.52] | +0.1876 | +0.188 | +0.938 | +1.876 | +3.753 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### v1 optimizer: treated opponent's cards as independent (old)

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 66.35% | 0.01% | 33.63% | 66.36% | [66.32, 66.40] | +0.1945 | +0.194 | +0.972 | +1.945 | +3.890 |
| Sharp B (mirror: same optimizer) | 0.00% | 100.00% | 0.00% | nan% | [nan, nan] | +0.0000 | +0.000 | +0.000 | +0.000 | +0.000 |
| Casual A (gut feel) | 61.99% | 0.25% | 37.76% | 62.15% | [62.11, 62.19] | +0.1183 | +0.118 | +0.592 | +1.183 | +2.367 |
| Casual B (degen) | 67.92% | 0.06% | 32.02% | 67.96% | [67.92, 68.00] | +0.2232 | +0.223 | +1.116 | +2.232 | +4.464 |
| Sharp C (match-aware, own model) | 77.89% | 1.75% | 20.37% | 79.27% | [79.24, 79.30] | +0.4194 | +0.419 | +2.097 | +4.194 | +8.388 |
| Near-mirror (this plan, bets +/-30%) | 44.74% | 8.19% | 47.07% | 48.73% | [48.69, 48.77] | -0.1128 | -0.113 | -0.564 | -1.128 | -2.256 |
| **Default mix** | 57.01% | 12.62% | 30.37% | 65.24% | [65.22, 65.27] | +0.1524 | +0.152 | +0.762 | +1.524 | +3.048 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### Baseline: basic strategy + 10 bets

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 45.69% | 11.05% | 43.26% | 51.37% | [51.32, 51.41] | -0.0670 | -0.067 | -0.335 | -0.670 | -1.341 |
| Sharp B (mirror: same optimizer) | 37.47% | 0.98% | 61.56% | 37.84% | [37.80, 37.88] | -0.3158 | -0.316 | -1.579 | -3.158 | -6.317 |
| Casual A (gut feel) | 53.95% | 0.62% | 45.44% | 54.28% | [54.24, 54.32] | -0.0228 | -0.023 | -0.114 | -0.228 | -0.456 |
| Casual B (degen) | 67.35% | 0.06% | 32.59% | 67.39% | [67.35, 67.43] | +0.2129 | +0.213 | +1.064 | +2.129 | +4.257 |
| Sharp C (match-aware, own model) | 18.61% | 0.02% | 81.37% | 18.62% | [18.58, 18.65] | -0.6648 | -0.665 | -3.324 | -6.648 | -13.296 |
| **Default mix** | 55.88% | 1.76% | 42.36% | 56.88% | [56.86, 56.90] | +0.0234 | +0.023 | +0.117 | +0.234 | +0.468 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### Baseline: basic strategy + flat 200

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 32.43% | 33.29% | 34.28% | 48.61% | [48.56, 48.66] | -0.0834 | -0.083 | -0.417 | -0.834 | -1.667 |
| Sharp B (mirror: same optimizer) | 38.67% | 0.31% | 61.02% | 38.79% | [38.75, 38.83] | -0.3008 | -0.301 | -1.504 | -3.008 | -6.017 |
| Casual A (gut feel) | 51.23% | 0.51% | 48.27% | 51.49% | [51.45, 51.53] | -0.0728 | -0.073 | -0.364 | -0.728 | -1.457 |
| Casual B (degen) | 63.87% | 3.77% | 32.35% | 66.38% | [66.34, 66.42] | +0.1875 | +0.187 | +0.937 | +1.875 | +3.749 |
| Sharp C (match-aware, own model) | 47.31% | 2.66% | 50.02% | 48.61% | [48.57, 48.65] | -0.1217 | -0.122 | -0.609 | -1.217 | -2.434 |
| **Default mix** | 52.05% | 5.80% | 42.15% | 55.26% | [55.23, 55.28] | -0.0050 | -0.005 | -0.025 | -0.050 | -0.101 |

Default-mix verdict (mix excludes near-mirror): **NOT profitable**

### Near-mirror stress test

Opponent runs this same plan but sizes every bet +/-30% (random per match): win 45.84%, tie 10.01%, loss 44.16%, **50.93% of decided** [50.89, 50.98] -> NOT profitable.

## Sharp-percentage sweeps (strategy re-optimized at every mix)

### Sharp = half Sharp A (flat basic) + half Sharp B (mirror)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 66.66% | [66.60, 66.72] | 0.19% | +0.1995 | 66.53% | 60.85% |
| 10% | 66.93% | [66.87, 66.99] | 5.18% | +0.1941 | 66.88% | 59.28% |
| 20% | 67.31% | [67.26, 67.37] | 10.18% | +0.1901 | 67.28% | 57.68% |
| 30% | 67.74% | [67.69, 67.79] | 15.17% | +0.1861 | 67.72% | 56.07% |
| 40% | 68.33% | [68.28, 68.38] | 20.16% | +0.1835 | 68.22% | 54.44% |
| 50% | 69.14% | [69.10, 69.19] | 25.14% | +0.1831 | 68.78% | 52.79% |
| 60% | 70.14% | [70.09, 70.19] | 30.16% | +0.1833 | 69.42% | 51.12% |
| 70% | 71.47% | [71.42, 71.52] | 35.17% | +0.1858 | 70.16% | 49.43% |
| 80% | 73.08% | [73.02, 73.13] | 40.14% | +0.1888 | 71.03% | 47.72% |
| 90% | 75.39% | [75.32, 75.45] | 45.20% | +0.1956 | 72.05% | 45.99% |
| 100% | 77.66% | [77.58, 77.74] | 50.18% | +0.1982 | 73.28% | 44.24% |

Break-even (point estimate): **never (profitable at every mix tested)**; break-even using the 99% CI lower bound: **never (profitable at every mix tested)**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

### STRESS: Sharp = Sharp C (match-aware player with its own model)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 66.70% | [66.64, 66.76] | 0.18% | +0.2002 | - | - |
| 10% | 67.37% | [67.32, 67.43] | 0.18% | +0.2124 | - | - |
| 20% | 68.84% | [68.79, 68.89] | 0.20% | +0.2386 | - | - |
| 30% | 70.27% | [70.22, 70.31] | 0.18% | +0.2643 | - | - |
| 40% | 71.91% | [71.86, 71.95] | 0.17% | +0.2938 | - | - |
| 50% | 74.06% | [74.02, 74.11] | 0.26% | +0.3323 | - | - |
| 60% | 76.03% | [75.98, 76.08] | 0.27% | +0.3675 | - | - |
| 70% | 77.98% | [77.93, 78.03] | 0.28% | +0.4024 | - | - |
| 80% | 79.98% | [79.92, 80.03] | 0.30% | +0.4383 | - | - |
| 90% | 82.00% | [81.94, 82.06] | 0.33% | +0.4745 | - | - |
| 100% | 83.98% | [83.91, 84.04] | 0.34% | +0.5099 | - | - |

Break-even (point estimate): **never (profitable at every mix tested)**; break-even using the 99% CI lower bound: **never (profitable at every mix tested)**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

### STRESS: Sharp = near-mirror (this same plan, bets +/-30%)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 66.65% | [66.59, 66.71] | 0.18% | +0.1993 | - | - |
| 10% | 65.43% | [65.38, 65.49] | 0.94% | +0.1761 | - | - |
| 20% | 64.18% | [64.12, 64.23] | 1.70% | +0.1525 | - | - |
| 30% | 62.86% | [62.81, 62.91] | 2.44% | +0.1283 | - | - |
| 40% | 61.59% | [61.54, 61.64] | 3.21% | +0.1051 | - | - |
| 50% | 60.27% | [60.22, 60.33] | 3.95% | +0.0816 | - | - |
| 60% | 58.92% | [58.86, 58.98] | 4.72% | +0.0577 | - | - |
| 70% | 57.53% | [57.46, 57.59] | 5.48% | +0.0335 | - | - |
| 80% | 56.12% | [56.05, 56.20] | 6.23% | +0.0096 | - | - |
| 90% | 54.69% | [54.60, 54.77] | 7.00% | -0.0145 | - | - |
| 100% | 47.08% | [46.98, 47.18] | 13.61% | -0.1318 | - | - |

Break-even (point estimate): **84% sharp**; break-even using the 99% CI lower bound: **83% sharp**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

## Sensitivity: strategy optimized for mix X, played against opponent Y (win% of decided)

| Optimized for | Sharp A (basic, flat bets) | Casual A (gut feel) | Casual B (degen) | Sharp C (match-aware, own model) | Near-mirror (this plan, bets +/-30%) | Default mix |
|---|---|---|---|---|---|---|
| default | 73.27% | 64.66% | 68.36% | 60.22% | 50.92% | 67.48% |
| all_casual | 69.04% | 64.69% | 68.68% | 63.41% | 53.25% | 67.02% |
| 50%_sharp | 75.46% | 63.82% | 68.12% | 54.57% | 48.43% | 67.33% |
| only_sharp_a | 77.69% | 61.28% | 66.46% | 45.14% | 47.03% | 65.84% |
| only_casual_a | 69.93% | 64.99% | 62.98% | 61.73% | 45.61% | 64.95% |
| only_casual_b | 38.59% | 37.13% | 73.31% | 46.50% | 48.21% | 52.85% |
| with_25%_sharp_c | 67.70% | 63.44% | 68.47% | 80.18% | 56.85% | 66.21% |

## Robustness: default plan vs opponents it was NOT tuned for

| Opponent variant | v2 win% decided | 99% CI | v1 (old) | Basic+min bets |
|---|---|---|---|---|
| Casual A, bets 20/40/75/125/175, fewer mistakes | 67.34% | [67.25, 67.42] | 64.71% | 53.11% |
| Casual A, bets 100-500 | 55.35% | [55.26, 55.45] | 56.55% | 55.59% |
| Degen, exactly one all-in, small sides | 54.54% | [54.45, 54.63] | 54.51% | 53.29% |
| Sharp, basic strategy, bets 10-30 flat | 67.40% | [67.32, 67.49] | 73.07% | 51.36% |
| Sharp, basic strategy, flat 300-500 | 53.46% | [53.37, 53.56] | 58.90% | 55.62% |
| Sharp, basic strategy, flat 35/65/135/240 | 69.22% | [69.14, 69.30] | 63.71% | 51.44% |

## Rule assumptions (default mix, re-optimized)

| Variant | Win% decided | 99% CI | Basic EV/hand |
|---|---|---|---|
| Default rules | 67.49% | [67.47, 67.52] | -0.547% |
| no_peek | 67.59% | [67.54, 67.65] | -0.615% |
| dealer_draws_if_all_bust | 67.48% | [67.43, 67.53] | -0.512% |
| split_by_value | 67.50% | [67.44, 67.55] | -0.512% |

## Bankroll ($500), 2,000-match horizon

### Default mix

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | +0.188 | 0.0% | 0.0% | $875 | $817 |
| $5 | +0.938 | 0.0% | 0.0% | $2,376 | $2,079 |
| $10 | +1.876 | 0.0% | 0.0% | $4,257 | $3,666 |
| $20 | +3.753 | 0.0% | 0.0% | $8,012 | $6,868 |

### Stress mix (50% near-mirror players, 50% casuals)

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | +0.082 | 0.0% | 0.0% | $663 | $600 |
| $5 | +0.408 | 0.0% | 0.0% | $1,314 | $994 |
| $10 | +0.816 | 0.0% | 0.0% | $2,134 | $1,492 |
| $20 | +1.631 | 0.3% | 0.6% | $3,772 | $2,476 |

## Entry-size recommendation ($500 bankroll)

- Under the default mix, every entry size has under 1% simulated risk of ruin on $500 (largest passing: $20). Required bankroll for <1% ruin is about **8 entries** (diffusion approximation): $8 for $1, $38 for $5, $77 for $10, $154 for $20.
- **But the model's edge is unproven in the real pool.** Start at **$1** until the dashboard shows 200+ logged decided matches with the real 99% CI lower bound above 55.56%. Then move to $5. Move to $10 only with 400+ matches still above break-even and a bankroll of at least 100 entries ($1,000). Use $20 only above $2,000.
- Move down one level if bankroll drops below 50 entries of the current level, or if the real win rate's 99% CI upper bound drops below 55.56% (you're losing), or if the real rate sits far below the sim prediction (the model is wrong about the pool).
- Worst realistic case: if most opponents are near-mirror players, the win rate is 50.93% of decided matches. That loses money at every entry size.
