"""
Builds the static strategy tables for a rule set.

* dealer final-total distribution per upcard (infinite-deck approximation,
  stands on all 17s, conditioned on "no blackjack" when the dealer peeks)
* chip-EV basic strategy, derived by running the engine's own expectimax with
  a linear value function (so basic strategy and the match optimizer share code)
* final-category distributions for split sub-hands (used to value splits)
* exact side-stake probabilities from a finite 6-deck shoe
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations_with_replacement
from math import comb

import numpy as np

from . import core
from .config import Rules

PRF = [0.0] + [1 / 13] * 9 + [4 / 13]


def dealer_dist(up: int, peek: bool) -> np.ndarray:
    """Distribution over dealer categories 0..4 = 17..21, 5 = bust, 6 = blackjack."""
    out = np.zeros(7)

    def draw(h, a, p, n):
        t = h + 10 if (a and h + 10 <= 21) else h
        if n == 2 and t == 21:
            out[6] += p
            return
        if t > 21:
            out[5] += p
            return
        if t >= 17:
            out[t - 17] += p
            return
        for r in range(1, 11):
            draw(h + r, a or r == 1, p * PRF[r], n + 1)

    # first draw = hole card, possibly conditioned on the peek
    weights = PRF.copy()
    if peek and up == 1:
        weights[10] = 0.0
    if peek and up == 10:
        weights[1] = 0.0
    tot = sum(weights)
    for r in range(1, 11):
        if weights[r] > 0:
            draw(up + r, up == 1 or r == 1, weights[r] / tot, 2)
    return out


@dataclass
class Tables:
    R: np.ndarray        # packed rules
    D: np.ndarray        # [11, 7] dealer dist by upcard value
    act2: np.ndarray     # [23, 2, 11] basic action on first two cards (double allowed)
    actN: np.ndarray     # [23, 2, 11] basic action, no double
    splt: np.ndarray     # [11, 11] 1 = split this pair value vs upcard
    subd: np.ndarray     # [2(das), 11(pair), 11(up), 14] split sub-hand final categories
    ev2: np.ndarray      # [23, 2, 11, 3] chip EV per unit of stand/hit/double (for display)
    evsplit: np.ndarray  # [11, 11] chip EV per unit of splitting


def _linear_V():
    return np.arange(4000, dtype=np.float64) * core.CHIP   # V(x) = x


def build_tables(rules: Rules) -> Tables:
    R = rules.as_int_array()
    D = np.zeros((11, 7))
    for u in range(1, 11):
        D[u] = dealer_dist(u, rules.dealer_peeks)

    V = _linear_V()
    base, b = 5000.0, 10.0
    offs = np.array([base, 0, 0, 0.0])
    offp = np.array([1.0, 0, 0, 0])
    inspay = np.zeros(7)
    act2 = np.zeros((23, 2, 11), dtype=np.int64)
    actN = np.zeros((23, 2, 11), dtype=np.int64)
    ev2 = np.zeros((23, 2, 11, 3))
    for u in range(1, 11):
        stv = np.zeros((23, 2)); hitv = np.zeros((23, 2)); dblv = np.zeros((23, 2)); best = np.zeros((23, 2))
        core.hand_tables(V, offs, offp, 1, D[u], inspay, b, stv, hitv, dblv, best)
        for h in range(2, 22):
            for a in range(2):
                st, hv, dv = stv[h, a], hitv[h, a], dblv[h, a]
                ev2[h, a, u] = [(st - base) / b, (hv - base) / b, (dv - base) / b]
                t = core.best_total(h, a)
                actN[h, a, u] = core.STAND if (t >= 21 or st >= hv) else core.HIT
                act2[h, a, u] = actN[h, a, u]
                if core.double_ok(h, a, R) and t < 21:
                    if dv > max(st, hv) + 1e-12:
                        act2[h, a, u] = core.DOUBLE

    subd = np.zeros((2, 11, 11, 14))
    for das in range(2):
        for pv in range(1, 11):
            for u in range(1, 11):
                subd[das, pv, u] = _subhand_dist(pv, u, das == 1 and rules.double_after_split,
                                                 act2, actN, R)

    splt = np.zeros((11, 11), dtype=np.int64)
    evsplit = np.zeros((11, 11))
    das_idx = 1 if rules.double_after_split else 0
    for u in range(1, 11):
        stv = np.zeros((23, 2)); hitv = np.zeros((23, 2)); dblv = np.zeros((23, 2)); best = np.zeros((23, 2))
        core.hand_tables(V, offs, offp, 1, D[u], inspay, b, stv, hitv, dblv, best)
        for pv in range(1, 11):
            sv = core.split_value(V, offs, offp, 1, D[u], inspay, b, subd[das_idx, pv, u])
            h, a = 2 * pv, 1 if pv == 1 else 0
            nosplit = max(stv[h, a], hitv[h, a], dblv[h, a] if core.double_ok(h, a, R) else -1e18)
            evsplit[pv, u] = (sv - base) / b
            splt[pv, u] = 1 if sv > nosplit + 1e-9 else 0
    return Tables(R, D, act2, actN, splt, subd, ev2, evsplit)


def _subhand_dist(pv, u, das, act2, actN, R) -> np.ndarray:
    """Final category distribution (mult_idx*7 + pc) of one split sub-hand under basic strategy."""
    out = np.zeros(14)

    def cat(h, a):
        return core.cat_of(h, a)

    def play(h, a, n, p):
        t = core.best_total(h, a)
        if t > 21:
            out[0] += p
            return
        if t == 21:
            out[cat(h, a)] += p
            return
        if n == 2 and das and core.double_ok(h, a, R):
            act = act2[h, a, u]
        else:
            act = actN[h, a, u]
        if act == core.STAND:
            out[cat(h, a)] += p
        elif act == core.DOUBLE:
            for r in range(1, 11):
                nh, na = h + r, 1 if (a or r == 1) else 0
                out[7 + cat(nh, na)] += p * PRF[r]
        else:
            for r in range(1, 11):
                play(h + r, 1 if (a or r == 1) else 0, n + 1, p * PRF[r])

    for r in range(1, 11):
        h, a = pv + r, 1 if (pv == 1 or r == 1) else 0
        if pv == 1:      # split aces: one card each, no further action
            out[cat(h, a)] += PRF[r]
        else:
            play(h, a, 2, PRF[r])
    return out


# ----------------------------------------------------------------------------
# Exact side-stake math (finite 6-deck shoe, top of shoe)
# ----------------------------------------------------------------------------
def perfect_pairs_exact(decks=6):
    """Returns dict of exact probabilities and EV per unit staked."""
    n = 52 * decks
    same_suit = decks - 1             # other cards of same rank+suit
    same_color = decks                # same rank, the other suit of the same color
    other_color = 2 * decks           # same rank, opposite color
    p_perfect = Fraction(same_suit, n - 1)
    p_colored = Fraction(same_color, n - 1)
    p_mixed = Fraction(other_color, n - 1)
    p_none = 1 - p_perfect - p_colored - p_mixed
    ev = 25 * p_perfect + 12 * p_colored + 6 * p_mixed - p_none
    return {"perfect": float(p_perfect), "colored": float(p_colored), "mixed": float(p_mixed),
            "none": float(p_none), "ev": float(ev), "ev_exact": str(ev)}


def four_card_total_exact(decks=6):
    """Exact distribution of the 4-card total (A=11) for 4 cards drawn from a fresh shoe."""
    counts = {v: 4 * decks for v in range(2, 10)}
    counts[10] = 16 * decks
    counts[11] = 4 * decks
    n = 52 * decks
    total = comb(n, 4)
    cats = [Fraction(0)] * 4
    for combo in combinations_with_replacement(sorted(counts), 4):
        ways = 1
        for v in set(combo):
            ways *= comb(counts[v], combo.count(v))
        s = sum(combo)
        k = 3 if s >= 40 else 2 if s >= 38 else 1 if s >= 36 else 0
        cats[k] += Fraction(ways, total)
    mult = [-1, 2, 8, 10]
    ev = sum(m * p for m, p in zip(mult, cats))
    return {"p": [float(c) for c in cats], "ev": float(ev), "ev_exact": str(ev)}


ACT_NAMES = {core.STAND: "STAND", core.HIT: "HIT", core.DOUBLE: "DOUBLE", core.SPLIT: "SPLIT"}
