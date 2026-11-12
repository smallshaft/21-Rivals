"""
Engine tests.  Run:  python -m pytest -q
"""
import numpy as np
import pytest
from numba import njit

from rivals import core
from rivals.config import Rules, Profile
from rivals.strategy import (build_tables, dealer_dist, perfect_pairs_exact,
                             four_card_total_exact, PRF)

T = build_tables(Rules())
DUMMY = (np.zeros((5, 1)), np.zeros((5, 1)), np.zeros((5, 1)), np.zeros((6, 4)))


@njit
def nb_seed(s):
    np.random.seed(s)


# card helpers: rank 1..13, suit 0..3 -> card id
def C(rank, suit=0):
    return (rank - 1) * 4 + suit


def make_shoe(cards):
    """A custom shoe: given cards first, then filler (deterministic)."""
    shoe = np.array([i % 52 for i in range(312)], dtype=np.int64)
    shoe[:len(cards)] = cards
    return shoe


def flat(b):
    return Profile("t", bets=[b]).as_params()


def play(shoe, P, chips=1000.0, ptype=core.T_PARAM, h=0, rules=T):
    pst = np.zeros(6)
    core.init_pstate(P, pst)
    rec = np.zeros(4)
    c, ptr = core.play_hand(shoe, 0, chips, h, ptype, P, pst, rules.R, rules.D, rules.act2, rules.actN,
                            rules.splt, rules.subd, *DUMMY, rec)
    return c, ptr, rec


# ---------------------------------------------------------------------------
# basic strategy chart (6 decks, S17, DAS, double 9-11 only, no surrender, peek)
# ---------------------------------------------------------------------------
UPS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]
HARD = {  # total: actions vs 2..A
    8: "HHHHHHHHHH", 9: "HDDDDHHHHH", 10: "DDDDDDDDHH", 11: "DDDDDDDDDH",
    12: "HHSSSHHHHH", 13: "SSSSSHHHHH", 14: "SSSSSHHHHH", 15: "SSSSSHHHHH",
    16: "SSSSSHHHHH", 17: "SSSSSSSSSS",
}
# soft hands can't be doubled under these rules (A-x shows 13-20, not 9-11)
SOFT = {13: "HHHHHHHHHH", 17: "HHHHHHHHHH", 18: "SSSSSSSHHH", 19: "SSSSSSSSSS"}
PAIRS = {1: "PPPPPPPPPP", 2: "PPPPPP----", 3: "PPPPPP----", 4: "---PP-----", 5: "----------",
         6: "PPPPP-----", 7: "PPPPPP----", 8: "PPPPPPPPPP", 9: "PPPPP-PP--", 10: "----------"}
CODE = {"S": core.STAND, "H": core.HIT, "D": core.DOUBLE}


def test_basic_strategy_chart():
    for t, row in HARD.items():
        for u, a in zip(UPS, row):
            assert T.act2[t, 0, u] == CODE[a], f"hard {t} vs {u}"
    for t, row in SOFT.items():
        for u, a in zip(UPS, row):
            assert T.act2[t - 10, 1, u] == CODE[a], f"soft {t} vs {u}"
    for pv, row in PAIRS.items():
        for u, a in zip(UPS, row):
            assert T.splt[pv, u] == (1 if a == "P" else 0), f"pair {pv} vs {u}"


def test_dealer_distribution_sums():
    for peek in (True, False):
        for u in range(1, 11):
            d = dealer_dist(u, peek)
            assert abs(d.sum() - 1) < 1e-12
            if peek:
                assert d[6] == 0
    # published infinite-deck S17 dealer bust rates: vs 2 35.36%, vs 6 42.32%
    assert abs(dealer_dist(2, True)[5] - 0.3536) < 0.0005
    assert abs(dealer_dist(6, True)[5] - 0.4232) < 0.0005


def analytic_basic_ev(rules=Rules()):
    """Infinite-deck EV of basic strategy, computed by full enumeration of the deal."""
    t = build_tables(rules)
    ev = 0.0
    for u in range(1, 11):
        pbj = PRF[10] if u == 1 else PRF[1] if u == 10 else 0.0
        for c1 in range(1, 11):
            for c2 in range(1, 11):
                p = PRF[u] * PRF[c1] * PRF[c2]
                pbj_player = (c1 == 1 and c2 == 10) or (c1 == 10 and c2 == 1)
                if pbj_player:
                    ev += p * (1 - pbj) * 1.5
                    continue
                h, a = c1 + c2, 1 if (c1 == 1 or c2 == 1) else 0
                best = max(t.ev2[h, a, u, 0], t.ev2[h, a, u, 1])
                if core.double_ok(h, a, t.R):
                    best = max(best, t.ev2[h, a, u, 2])
                if c1 == c2:
                    best = max(best, t.evsplit[c1, u])
                ev += p * (pbj * -1.0 + (1 - pbj) * best)
    return ev


def test_house_edge_matches_known_values():
    """Published 6D S17 DAS no-surrender, full doubling, resplit to 4: ~0.40-0.45%.
    Double 9-11 only (+~0.09%) and no resplit (+~0.03-0.05%) -> expect ~0.50-0.60% for 6 decks.
    The infinite-deck figure is ~0.08-0.12% worse than 6 decks."""
    ev_inf = analytic_basic_ev()
    assert -0.0075 < ev_inf < -0.0055, ev_inf
    P = np.zeros(20); P[0] = 10; P[6] = 1; P[11] = 1; P[12] = 5; P[13] = 5; P[19] = 1e6
    j = core.sample_hands(3_000_000, 5, 32, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd,
                          np.zeros((1, 1)), np.zeros((6, 4)))
    p = j / j.sum()
    units = (np.arange(21) - 10) / 2
    ev_sim = (p.sum(axis=(1, 2)) * units).sum()
    # 6-deck vs infinite deck differ by a few hundredths of a percent; SE ~0.07%
    assert abs(ev_sim - ev_inf) < 0.0030, (ev_sim, ev_inf)
    assert -0.0075 < ev_sim < -0.0040


def test_side_stakes_exact_vs_sim():
    pp = perfect_pairs_exact()
    assert pp["ev_exact"] == "-19/311"          # 25*5/311 + 12*6/311 + 6*12/311 - 288/311
    fc = four_card_total_exact()
    assert abs(sum(fc["p"]) - 1) < 1e-12
    P = np.zeros(20); P[0] = 10; P[6] = 1; P[11] = 1; P[12] = 5; P[13] = 5; P[19] = 1e6
    j = core.sample_hands(4_000_000, 6, 32, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd,
                          np.zeros((1, 1)), np.zeros((6, 4)))
    p = j / j.sum()
    pps = p.sum(axis=(0, 2)); fcs = p.sum(axis=(0, 1))
    assert abs((pps * core.PP_MULT).sum() - pp["ev"]) < 0.008     # ~4 standard errors
    assert abs((fcs * core.FC_MULT).sum() - fc["ev"]) < 0.006
    for k in range(4):
        assert abs(fcs[k] - fc["p"][k]) < 0.002


# ---------------------------------------------------------------------------
# hand mechanics on hand-built shoes
# ---------------------------------------------------------------------------
def test_blackjack_pays_3_to_2():
    shoe = make_shoe([C(1), C(9), C(13), C(7)])    # P: A,K  D: 9,7
    c, ptr, rec = play(shoe, flat(100))
    assert c == 1150 and ptr == 4


def test_dealer_peek_blackjack_loses_only_stake():
    shoe = make_shoe([C(10), C(1), C(10), C(13)])   # P: 10,10  D: A up, K hole
    c, ptr, _ = play(shoe, flat(100))
    assert c == 900 and ptr == 4


def test_stand_and_dealer_draws_from_shoe():
    # P: 10,6 (16) vs D 6 up, 10 hole -> basic stands; dealer 16 draws shoe[4]=5 -> 21
    shoe = make_shoe([C(10), C(6), C(6), C(10), C(5)])
    c, ptr, _ = play(shoe, flat(100))
    assert c == 900 and ptr == 5


def test_double_only_on_9_to_11():
    # P: 6,5 = 11 vs 6 -> double; gets 10 -> 21; dealer 6,10 draws 9 -> bust
    shoe = make_shoe([C(6), C(6), C(5), C(10), C(10), C(9)])
    c, ptr, _ = play(shoe, flat(100))
    assert c == 1200 and ptr == 6
    # 8 (5,3) vs 6: double not allowed -> hits
    shoe = make_shoe([C(5), C(6), C(3), C(10), C(10), C(9)])   # 5,3 + 10 = 18, dealer 16 + 9 bust
    c, ptr, _ = play(shoe, flat(100))
    assert c == 1100 and ptr == 6


def test_split_aces_one_card_each():
    # P: A,A vs 6 -> split; A+9 = 20, A+8 = 19, no more cards; dealer 6,10 + 7 = 23 bust
    shoe = make_shoe([C(1), C(6), C(1, 1), C(10), C(9), C(8), C(7)])
    c, ptr, _ = play(shoe, flat(100))
    assert c == 1200 and ptr == 7


def test_double_after_split():
    # P: 8,8 vs 6 -> split. hand1: 8+3=11 -> double -> +10 = 21. hand2: 8+10=18 stand.
    # dealer 6,10 + 9 -> bust: +200 +100
    shoe = make_shoe([C(8), C(6), C(8, 2), C(10), C(3), C(10), C(10, 1), C(9)])
    c, ptr, _ = play(shoe, flat(100))
    assert c == 1300 and ptr == 8


def test_cannot_double_without_chips():
    # all-in 100 with 100 chips: 11 vs 6 must hit (one card, then decide), not double
    shoe = make_shoe([C(6), C(6), C(5), C(10), C(10), C(9)])
    c, ptr, _ = play(shoe, flat(100), chips=100.0)
    assert c == 200   # won 100, not 200


def test_side_stakes_resolve_independently():
    # perfect pair of 9s (same suit) pays 25:1 even though the main hand loses
    P = Profile("t", bets=[10], p_side=1.0, side_min=5, side_max=5).as_params()
    nb_seed(1)
    shoe = make_shoe([C(9, 0), C(10), C(9, 0), C(10)])   # 18 vs 20 (9,9 vs 10: stand)
    c, ptr, rec = play(shoe, P)
    # main -10.  PP perfect +125.  4CT 9+9+10+10 = 38 -> 8:1 -> +40
    assert rec[1] == 3 and rec[2] == 2
    assert c == 1000 - 10 + 125 + 40 and ptr == 4


# ---------------------------------------------------------------------------
# shared-shoe divergence
# ---------------------------------------------------------------------------
def test_mirror_match_is_always_a_tie():
    P = flat(100)
    wtl, _, _ = core.simulate(20000, 3, 8, core.T_PARAM, P, core.T_PARAM, P, T.R, T.D, T.act2,
                              T.actN, T.splt, T.subd, *DUMMY, 100, *DUMMY)
    assert wtl.sum(axis=0)[1] == 20000


def test_same_decisions_means_same_cards():
    """Flat 10 vs flat 20, both basic strategy, always affordable: every result must
    scale exactly 2x, proving both players saw identical cards."""
    P10, P20 = flat(10), flat(20)
    rec = np.zeros(4); tr = np.zeros(5)
    nb_seed(42)
    shoe = np.empty(312, dtype=np.int64)
    for _ in range(3000):
        core.make_shoe(shoe)
        pa = np.zeros(6); pb = np.zeros(6)
        core.init_pstate(P10, pa); core.init_pstate(P20, pb)
        ca = core.play_match_player(shoe, core.T_PARAM, P10, T.R, T.D, T.act2, T.actN, T.splt,
                                    T.subd, *DUMMY, pa, rec, tr)
        cb = core.play_match_player(shoe, core.T_PARAM, P20, T.R, T.D, T.act2, T.actN, T.splt,
                                    T.subd, *DUMMY, pb, rec, tr)
        assert (ca - 1000) * 2 == cb - 1000


def test_divergence_each_player_reads_own_position():
    """Player A stands 16 vs 10 (a 'mistake' via p_stand_stiff=1), player B hits.
    B consumes shoe[4]; the dealer then draws for A from shoe[4] but for B from shoe[5]."""
    shoe = make_shoe([C(10), C(10), C(6), C(6), C(4), C(5), C(2)])
    # A stands 16: dealer 10,6 = 16 draws shoe[4]=4 -> 20. A loses.
    PA = Profile("a", bets=[100], p_stand_stiff=1.0).as_params()
    nb_seed(0)
    ca, pa_ptr, _ = play(shoe, PA)
    assert ca == 900 and pa_ptr == 5
    # B hits 16: gets 4 -> 20, stands. Dealer 16 draws shoe[5]=5 -> 21. B loses.
    cb, pb_ptr, _ = play(shoe, flat(100))
    assert cb == 900 and pb_ptr == 6


def test_optimizer_mirror_ties():
    from rivals.config import Settings
    from rivals import optimizer as O
    s = Settings()
    plan = O.build_plan(s, n_opp=100_000, iters=1, T=T, verbose=False)
    tabs = (plan.bet, plan.pp, plan.fc, plan.Vall)
    wtl, _, _ = core.simulate(20000, 9, 8, core.T_OPT, core.ZP, core.T_OPT, core.ZP, T.R, T.D,
                              T.act2, T.actN, T.splt, T.subd, *tabs, O.NV, *tabs)
    assert wtl.sum(axis=0)[1] == 20000
    # plan sanity: bets are legal (multiples of 5, >= 10, wagers <= chips)
    for h in range(5):
        for ci in range(4, 4000, 37):
            c = ci * 2.5
            b, s1, s2 = plan.bet[h, ci], plan.pp[h, ci], plan.fc[h, ci]
            assert b % 5 == 0 and b >= 10 and b + s1 + s2 <= c + 1e-9


# ---------------------------------------------------------------------------
# v2 (correlation-aware) plan
# ---------------------------------------------------------------------------
def test_result_classes():
    assert [core.xclass(x) for x in (-4, -2, -1, 0, 1, 1.5, 2, 3)] == [0, 0, 1, 2, 3, 4, 5, 5]


def test_tree_plan_mirror_ties_and_history_tracking():
    from rivals import corr
    from rivals.config import Settings
    tp = corr.build_tree_plan(Settings(), n_per_type=100_000, verbose=False, T=T)
    tabs = tp.engine_tables()
    P = corr.tree_player_params()
    wtl, _, _ = core.simulate(20000, 5, 8, core.T_OPT, P, core.T_OPT, P, T.R, T.D, T.act2,
                              T.actN, T.splt, T.subd, *tabs, 10, *tabs)
    assert wtl.sum(axis=0)[1] == 20000
    # replay matches by hand: the engine's bet each hand must equal the table entry for
    # the node built from this match's earlier results (what the advisor does)
    rec = np.zeros(4); tr = np.zeros(5); pst = np.zeros(6)
    nb_seed(3)
    shoe = np.empty(312, dtype=np.int64)
    for _ in range(300):
        core.make_shoe(shoe)
        core.play_match_player(shoe, core.T_OPT, P, T.R, T.D, T.act2, T.actN, T.splt, T.subd,
                               *tabs, pst, rec, tr)
        c, hist = 1000.0, []
        for h in range(5):
            nd = corr.node_id(h, corr.history_code(hist))
            b = float(tp.bet[nd, int(round(c / 2.5))])
            if c >= 10:
                x = (tr[h] - c) / b
                assert abs(x * 2 - round(x * 2)) < 1e-9     # result is a whole number of half-bets
                hist.append(x)
            c = tr[h]
