# 21 Rivals - simulation report

Matches per main matchup: **300,000**, per sweep/sensitivity cell: 200,000. Fixed seeds. Break-even = 55.56% of decided matches (ties refund).

## Engine checks

- Basic strategy EV per hand (sim, 2,000,000 hands): **-0.533%** (+/- 0.205% at 99%). Published 6-deck S17 DAS no-surrender is about -0.40% to -0.45% with full doubling; restricting doubles to 9-11 and one split costs about another 0.10-0.15%, so ~-0.55% is expected.
- Perfect Pairs: exact EV -6.109% (-19/311), sim -6.430%
- 4-Card Total: exact EV -4.487%, sim -4.644%

## Head-to-head results (exact shared-shoe simulation)

### v2 optimizer: prices in the shared cards (this app)

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 74.16% | 0.13% | 25.71% | 74.26% | [74.05, 74.46] | +0.3362 | +0.336 | +1.681 | +3.362 | +6.724 |
| Sharp B (mirror: same optimizer) | 0.00% | 100.00% | 0.00% | nan% | [nan, nan] | +0.0000 | +0.000 | +0.000 | +0.000 | +0.000 |
| Casual A (gut feel) | 63.97% | 0.37% | 35.66% | 64.21% | [63.98, 64.43] | +0.1551 | +0.155 | +0.776 | +1.551 | +3.103 |
| Casual B (degen) | 68.18% | 0.08% | 31.74% | 68.23% | [68.01, 68.45] | +0.2280 | +0.228 | +1.140 | +2.280 | +4.561 |
| Sharp C (match-aware, own model) | 57.45% | 0.86% | 41.69% | 57.95% | [57.72, 58.18] | +0.0427 | +0.043 | +0.214 | +0.427 | +0.855 |
| Near-mirror (this plan, bets +/-30%) | 44.40% | 11.06% | 44.53% | 49.93% | [49.68, 50.18] | -0.0901 | -0.090 | -0.451 | -0.901 | -1.802 |
| **Default mix** | 58.83% | 12.68% | 28.49% | 67.37% | [67.23, 67.51] | +0.1857 | +0.186 | +0.929 | +1.857 | +3.714 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### v1 optimizer: treated opponent's cards as independent (old)

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 66.53% | 0.01% | 33.46% | 66.54% | [66.32, 66.76] | +0.1977 | +0.198 | +0.988 | +1.977 | +3.954 |
| Sharp B (mirror: same optimizer) | 0.00% | 100.00% | 0.00% | nan% | [nan, nan] | +0.0000 | +0.000 | +0.000 | +0.000 | +0.000 |
| Casual A (gut feel) | 62.05% | 0.25% | 37.70% | 62.21% | [61.98, 62.43] | +0.1194 | +0.119 | +0.597 | +1.194 | +2.388 |
| Casual B (degen) | 68.02% | 0.06% | 31.92% | 68.06% | [67.84, 68.28] | +0.2250 | +0.225 | +1.125 | +2.250 | +4.500 |
| Sharp C (match-aware, own model) | 77.87% | 1.79% | 20.35% | 79.28% | [79.09, 79.48] | +0.4195 | +0.419 | +2.097 | +4.195 | +8.389 |
| Near-mirror (this plan, bets +/-30%) | 44.72% | 8.22% | 47.05% | 48.73% | [48.49, 48.98] | -0.1127 | -0.113 | -0.564 | -1.127 | -2.255 |
| **Default mix** | 57.09% | 12.62% | 30.29% | 65.34% | [65.20, 65.48] | +0.1539 | +0.154 | +0.769 | +1.539 | +3.077 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### Baseline: basic strategy + 10 bets

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 45.73% | 11.02% | 43.25% | 51.39% | [51.14, 51.64] | -0.0667 | -0.067 | -0.333 | -0.667 | -1.334 |
| Sharp B (mirror: same optimizer) | 40.09% | 0.74% | 59.17% | 40.39% | [40.16, 40.62] | -0.2709 | -0.271 | -1.355 | -2.709 | -5.419 |
| Casual A (gut feel) | 54.03% | 0.61% | 45.36% | 54.36% | [54.12, 54.59] | -0.0214 | -0.021 | -0.107 | -0.214 | -0.428 |
| Casual B (degen) | 67.36% | 0.06% | 32.57% | 67.40% | [67.18, 67.62] | +0.2131 | +0.213 | +1.066 | +2.131 | +4.263 |
| Sharp C (match-aware, own model) | 18.63% | 0.02% | 81.35% | 18.64% | [18.45, 18.82] | -0.6645 | -0.664 | -3.322 | -6.645 | -13.289 |
| **Default mix** | 56.25% | 1.72% | 42.03% | 57.23% | [57.11, 57.36] | +0.0297 | +0.030 | +0.149 | +0.297 | +0.594 |

Default-mix verdict (mix excludes near-mirror): **PROFITABLE (99% CI above 55.56%)**

### Baseline: basic strategy + flat 200

| Opponent | Win | Tie | Loss | Win% of decided | 99% CI | EV per $1 entry | $1 | $5 | $10 | $20 |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharp A (basic, flat bets) | 32.50% | 33.43% | 34.08% | 48.81% | [48.52, 49.10] | -0.0808 | -0.081 | -0.404 | -0.808 | -1.616 |
| Sharp B (mirror: same optimizer) | 38.80% | 0.17% | 61.03% | 38.86% | [38.64, 39.09] | -0.2999 | -0.300 | -1.500 | -2.999 | -5.999 |
| Casual A (gut feel) | 51.30% | 0.49% | 48.21% | 51.55% | [51.32, 51.79] | -0.0717 | -0.072 | -0.358 | -0.717 | -1.434 |
| Casual B (degen) | 63.64% | 3.86% | 32.50% | 66.19% | [65.97, 66.42] | +0.1841 | +0.184 | +0.921 | +1.841 | +3.682 |
| Sharp C (match-aware, own model) | 47.38% | 2.65% | 49.98% | 48.66% | [48.43, 48.90] | -0.1208 | -0.121 | -0.604 | -1.208 | -2.415 |
| **Default mix** | 52.02% | 5.83% | 42.16% | 55.23% | [55.10, 55.37] | -0.0054 | -0.005 | -0.027 | -0.054 | -0.109 |

Default-mix verdict (mix excludes near-mirror): **NOT profitable**

### Near-mirror stress test

Opponent runs this same plan but sizes every bet +/-30% (random per match): win 44.40%, tie 11.06%, loss 44.53%, **49.93% of decided** [49.68, 50.18] -> NOT profitable.

## Sharp-percentage sweeps (strategy re-optimized at every mix)

### Sharp = half Sharp A (flat basic) + half Sharp B (mirror)

| Sharp % | Win% decided | 99% CI | Tie% | EV per $1 | Fixed default plan | Basic+min bets |
|---|---|---|---|---|---|---|
| 0% | 66.47% | [66.27, 66.66] | 0.19% | +0.1960 | 66.22% | 60.90% |
| 10% | 66.93% | [66.75, 67.12] | 5.19% | +0.1942 | 66.65% | 59.45% |
| 20% | 67.28% | [67.11, 67.45] | 10.17% | +0.1896 | 67.12% | 57.98% |
| 30% | 67.63% | [67.46, 67.79] | 15.17% | +0.1843 | 67.64% | 56.49% |
| 40% | 68.32% | [68.16, 68.48] | 20.16% | +0.1834 | 68.23% | 54.99% |
| 50% | 69.05% | [68.89, 69.20] | 25.15% | +0.1817 | 68.90% | 53.46% |
| 60% | 70.08% | [69.93, 70.23] | 30.13% | +0.1827 | 69.67% | 51.93% |
| 70% | 71.36% | [71.20, 71.52] | 35.13% | +0.1846 | 70.55% | 50.37% |
| 80% | 72.86% | [72.68, 73.03] | 40.11% | +0.1865 | 71.58% | 48.80% |
| 90% | 74.84% | [74.64, 75.04] | 45.20% | +0.1903 | 72.80% | 47.20% |
| 100% | 76.65% | [76.41, 76.90] | 50.12% | +0.1894 | 74.26% | 45.59% |

Break-even (point estimate): **never (profitable at every mix tested)**; break-even using the 99% CI lower bound: **never (profitable at every mix tested)**. Same for every entry size: all four pay 1.8x, so the rake is 10% at every level.

## Sensitivity: strategy optimized for mix X, played against opponent Y (win% of decided)

| Optimized for | Sharp A (basic, flat bets) | Casual A (gut feel) | Casual B (degen) | Sharp C (match-aware, own model) | Near-mirror (this plan, bets +/-30%) | Default mix |
|---|---|---|---|---|---|---|
| default | 74.12% | 64.40% | 68.19% | 58.15% | 50.07% | 67.42% |
| only_casual_b | 36.30% | 36.10% | 72.96% | 48.20% | 46.94% | 51.93% |

## Rule assumptions (default mix, re-optimized)

| Variant | Win% decided | 99% CI | Basic EV/hand |
|---|---|---|---|
| Default rules | 67.37% | [67.23, 67.51] | -0.533% |
| no_peek | 67.47% | [67.30, 67.64] | -0.641% |

## Bankroll ($500), 2,000-match horizon

### Default mix

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | +0.186 | 0.0% | 0.0% | $871 | $813 |
| $5 | +0.929 | 0.0% | 0.0% | $2,357 | $2,059 |
| $10 | +1.857 | 0.0% | 0.0% | $4,218 | $3,624 |
| $20 | +3.714 | 0.0% | 0.0% | $7,936 | $6,792 |

### Stress mix (50% near-mirror players, 50% casuals)

| Entry | EV/match | P(ruin) in 200 | P(ruin) in 2000 | Median bankroll | 5th pct |
|---|---|---|---|---|---|
| $1 | +0.186 | 0.0% | 0.0% | $871 | $813 |
| $5 | +0.929 | 0.0% | 0.0% | $2,357 | $2,059 |
| $10 | +1.857 | 0.0% | 0.0% | $4,218 | $3,624 |
| $20 | +3.714 | 0.0% | 0.0% | $7,936 | $6,792 |

## Entry-size recommendation ($500 bankroll)

- Under the default mix, every entry size has under 1% simulated risk of ruin on $500 (largest passing: $20). Required bankroll for <1% ruin is about **8 entries** (diffusion approximation): $8 for $1, $39 for $5, $78 for $10, $155 for $20.
- **But the model's edge is unproven in the real pool.** Start at **$1** until the dashboard shows 200+ logged decided matches with the real 99% CI lower bound above 55.56%. Then move to $5. Move to $10 only with 400+ matches still above break-even and a bankroll of at least 100 entries ($1,000). Use $20 only above $2,000.
- Move down one level if bankroll drops below 50 entries of the current level, or if the real win rate's 99% CI upper bound drops below 55.56% (you're losing), or if the real rate sits far below the sim prediction (the model is wrong about the pool).
- Worst realistic case: if most opponents are near-mirror players, the win rate is 49.93% of decided matches. That loses money at every entry size.
