"""
Core engine (numba-compiled for speed).

Contents
--------
* Card encoding + the shared, fixed 6-deck shoe.
* Expectimax for in-hand decisions against an arbitrary (non-linear) value
  function V(chips).  With V(x) = x this is exactly chip-EV basic strategy;
  with V = "probability of beating the opponent" it gives match-aware play.
* play_hand(): plays one hand for one player from that player's own position
  in the shared shoe.  Two players with identical decisions consume identical
  cards; once they diverge each keeps reading the same fixed sequence from
  its own pointer (this is the shared-shuffle rule from the app).
* simulate(): plays N full head-to-head matches in parallel with fixed seeds.
* dp_step(): one backward step of the bet/side-stake dynamic program.

Card encoding: an int 0..51.  rank = c // 4 (0=A, 1=2, ... 12=K),
suit = c % 4 (0,1 red; 2,3 black).  Blackjack value: A=1 (soft logic), J/Q/K=10.

Dealer outcome categories k:   0..4 = final 17..21, 5 = bust, 6 = blackjack
Player outcome categories pc:  0 = bust, 1 = 16 or less, 2..6 = 17..21
"""
import numpy as np
from numba import njit, prange

CHIP = 2.5            # chip grid step
SHUF = 200            # we only shuffle the first 200 cards of 312 (a match never uses that many)
NDECK = 6

# infinite-deck draw probability by value 1..10 (index 0 unused)
PR = np.array([0.0] + [1.0 / 13] * 9 + [4.0 / 13])

# PAY[pc, k]: main-hand result in units of the stake, player category vs dealer category
PAY = np.zeros((7, 7))
for _pc in range(7):
    for _k in range(7):
        if _pc == 0:
            PAY[_pc, _k] = -1.0
        elif _k == 6:
            PAY[_pc, _k] = -1.0
        elif _k == 5:
            PAY[_pc, _k] = 1.0
        else:
            pt = 16 if _pc == 1 else 15 + _pc
            dt = 17 + _k
            PAY[_pc, _k] = 1.0 if pt > dt else (0.0 if pt == dt else -1.0)

# Side stake payouts (net multiple of the side stake), by category 0..3
PP_MULT = np.array([-1.0, 6.0, 12.0, 25.0])     # none, mixed, colored, perfect
FC_MULT = np.array([-1.0, 2.0, 8.0, 10.0])      # <36, 36-37, 38-39, 40+

# action codes
STAND, HIT, DOUBLE, SPLIT = 0, 1, 2, 3

# rules int array indices (see config.Rules.as_int_array)
R_PEEK, R_DAS, R_SPLITVAL, R_DOUBLESOFT, R_DRAWBUST = 0, 1, 2, 3, 4

# player types
T_OPT, T_PARAM = 0, 1


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
@njit(cache=True)
def cval(card):
    r = card // 4 + 1
    return 10 if r >= 10 else r


@njit(cache=True)
def fcval(card):
    """value for the 4-Card Total side stake: Ace = 11"""
    r = card // 4 + 1
    if r == 1:
        return 11
    return 10 if r >= 10 else r


@njit(cache=True)
def floor5(x):
    return 5.0 * np.floor(x / 5.0 + 1e-9)


@njit(cache=True)
def vget(V, x):
    i = int(x / CHIP + 0.5)
    if i < 0:
        i = 0
    n = V.shape[0]
    if i >= n:
        i = n - 1
    return V[i]


@njit(cache=True)
def best_total(h, a):
    if a and h + 10 <= 21:
        return h + 10
    return h


@njit(cache=True)
def cat_of(h, a):
    t = best_total(h, a)
    if t > 21:
        return 0
    if t <= 16:
        return 1
    return t - 15


@njit(cache=True)
def double_ok(h, a, R):
    if h < 9 or h > 11:
        return False
    if a and R[R_DOUBLESOFT] == 0:
        return False   # A-8 / A-9 show 19/20, not 9/10
    return True


@njit(cache=True)
def pp_cat(c1, c2):
    if c1 // 4 != c2 // 4:
        return 0
    if c1 % 4 == c2 % 4:
        return 3
    if (c1 % 4) // 2 == (c2 % 4) // 2:
        return 2
    return 1


@njit(cache=True)
def fc_cat_of_sum(s):
    if s >= 40:
        return 3
    if s >= 38:
        return 2
    if s >= 36:
        return 1
    return 0


@njit(cache=True)
def is_pair(c1, c2, R):
    if c1 // 4 == c2 // 4:
        return True
    if R[R_SPLITVAL] == 1 and cval(c1) == 10 and cval(c2) == 10:
        return True
    return False


# ----------------------------------------------------------------------------
# Expectimax against a value function V
# ----------------------------------------------------------------------------
@njit(cache=True)
def leaf_value(V, offs, offp, nq, Du, inspay, b, m, pc):
    """E[V(final chips)] if the player stands with category pc at multiplier m.
    offs/offp: mixture over uncertain 4-Card-Total side results (independent approx)."""
    s = 0.0
    for k in range(7):
        if Du[k] == 0.0:
            continue
        pay = m * b * PAY[pc, k] + inspay[k]
        acc = 0.0
        for q in range(nq):
            if offp[q] > 0.0:
                acc += offp[q] * vget(V, offs[q] + pay)
        s += Du[k] * acc
    return s


@njit(cache=True)
def hand_tables(V, offs, offp, nq, Du, inspay, b, stv, hitv, dblv, best):
    """Fill stand / hit / double / best value tables indexed [hard_total, ace_flag].
    Hitting always raises the hard total, so iterating totals downward works."""
    SV1 = np.empty(7)
    SV2 = np.empty(7)
    for pc in range(7):
        SV1[pc] = leaf_value(V, offs, offp, nq, Du, inspay, b, 1.0, pc)
        SV2[pc] = leaf_value(V, offs, offp, nq, Du, inspay, b, 2.0, pc)
    for h in range(21, 1, -1):
        for a in range(2):
            st = SV1[cat_of(h, a)]
            hv = 0.0
            dv = 0.0
            for r in range(1, 11):
                nh = h + r
                na = 1 if (a == 1 or r == 1) else 0
                if nh > 21:
                    hv += PR[r] * SV1[0]
                    dv += PR[r] * SV2[0]
                else:
                    hv += PR[r] * best[nh, na]
                    dv += PR[r] * SV2[cat_of(nh, na)]
            stv[h, a] = st
            hitv[h, a] = hv
            dblv[h, a] = dv
            if best_total(h, a) == 21:
                best[h, a] = st
            else:
                best[h, a] = st if st >= hv else hv


@njit(cache=True)
def split_value(V, offs, offp, nq, Du, inspay, b, sd):
    """Value of splitting: two independent sub-hands (played by basic strategy,
    final-category distribution sd[14] = mult_idx*7 + pc) vs one shared dealer."""
    s = 0.0
    for k in range(7):
        if Du[k] == 0.0:
            continue
        acc = 0.0
        for i in range(14):
            if sd[i] == 0.0:
                continue
            mi = 1.0 + (i // 7)
            pi = PAY[i % 7, k] * mi
            for j in range(14):
                if sd[j] == 0.0:
                    continue
                mj = 1.0 + (j // 7)
                pay = b * (pi + PAY[j % 7, k] * mj) + inspay[k]
                w = sd[i] * sd[j]
                for q in range(nq):
                    if offp[q] > 0.0:
                        acc += w * offp[q] * vget(V, offs[q] + pay)
        s += Du[k] * acc
    return s


# ----------------------------------------------------------------------------
# Parametric (basic strategy + human habits) decisions
# ----------------------------------------------------------------------------
@njit(cache=True)
def decide_param(h, a, n, pv, can_dbl, can_split, up, act2, actN, splt, P, R):
    if can_split and pv > 0 and splt[pv, up] == 1:
        if not (P[10] > 0.0 and np.random.random() < P[10]):
            return SPLIT
    t = best_total(h, a)
    if t >= 21:
        return STAND
    if n == 2 and can_dbl and double_ok(h, a, R):
        act = act2[h, a, up]
    else:
        act = actN[h, a, up]
    if act == DOUBLE and P[9] > 0.0 and np.random.random() < P[9]:
        act = actN[h, a, up]
    soft = a == 1 and h + 10 <= 21
    if act == HIT and (not soft) and t >= 12 and t <= 16 and (up >= 7 or up == 1):
        if P[8] > 0.0 and np.random.random() < P[8]:
            act = STAND
    if P[16] > 0.0 and t >= 12 and t <= 18 and (act == HIT or act == STAND):
        if np.random.random() < P[16]:
            act = HIT if act == STAND else STAND
    return act


# ----------------------------------------------------------------------------
# One hand for one player
# ----------------------------------------------------------------------------
@njit(cache=True)
def fc_mixture(c1, c2, up, R, offs, offp, base, sfc, exclude_val):
    """Distribution of the 4-Card-Total result given 3 visible cards; hole card
    unknown (exclude_val: hole value ruled out by the dealer's peek, or 0)."""
    if sfc <= 0.0:
        offs[0] = base
        offp[0] = 1.0
        return 1
    cnt = np.zeros(12)
    for v in range(2, 12):
        cnt[v] = 24.0 * NDECK / 6.0
    cnt[10] = 96.0 * NDECK / 6.0
    cnt[fcval(c1)] -= 1
    cnt[fcval(c2)] -= 1
    cnt[fcval(up)] -= 1
    if exclude_val == 1:
        cnt[11] = 0.0
    elif exclude_val == 10:
        cnt[10] = 0.0
    tot = cnt.sum()
    s3 = fcval(c1) + fcval(c2) + fcval(up)
    for q in range(4):
        offp[q] = 0.0
        offs[q] = base + sfc * FC_MULT[q]
    for v in range(2, 12):
        offp[fc_cat_of_sum(s3 + v)] += cnt[v] / tot
    return 4


@njit(cache=True)
def play_hand(shoe, ptr, c, hidx, ptype, P, pst, R, D, act2, actN, splt, subd,
              bet_tab, pp_tab, fc_tab, Vall, rec):
    """Play one hand. Returns (new_chips, new_ptr).
    rec (float[4]) receives: main net / bet, PP category, FC category, insurance taken."""
    rec[0] = 0.0
    rec[1] = -1.0
    rec[2] = -1.0
    rec[3] = 0.0
    rec[4] = 0.0
    rec[5] = 1.0
    rec[6] = 7.0
    if c < 10.0:
        return c, ptr

    # ---------------- bet sizing ----------------
    b = 10.0
    spp = 0.0
    sfc = 0.0
    # OPT variants for attribution: P[17]=1 no side stakes, P[18]=1 basic-strategy play
    useopt = ptype == T_OPT and P[18] == 0.0
    if ptype == T_OPT:
        ci = int(c / CHIP + 0.5)
        if ci < bet_tab.shape[1]:
            b = bet_tab[hidx, ci]
            spp = pp_tab[hidx, ci]
            sfc = fc_tab[hidx, ci]
        if P[17] == 1.0:
            spp = 0.0
            sfc = 0.0
        if P[12] > 0.0:      # per-match bet jitter (models a population of similar smart players)
            b = max(10.0, floor5(b * pst[0]))
    else:
        if pst[1 + hidx] == 1.0:
            b = floor5(c * P[15])
        elif P[6] == 1.0:
            b = pst[0]
        else:
            nb = 0
            for i in range(6):
                if P[i] > 0:
                    nb += 1
            b = P[int(np.random.random() * nb)]
        b = min(b, floor5(c))
        b = max(b, 10.0)
        for side in range(2):
            if P[11] > 0.0 and np.random.random() < P[11]:
                lo = int(P[12] / 5)
                hi = int(P[13] / 5)
                s = 5.0 * (lo + int(np.random.random() * (hi - lo + 1)))
                if s <= c - b - spp - sfc:
                    if side == 0:
                        spp = s
                    else:
                        sfc = s
    if b + spp + sfc > c:   # safety
        spp = 0.0
        sfc = 0.0
        b = min(b, floor5(c))
    free = c - b - spp - sfc

    # ---------------- deal ----------------
    p1 = shoe[ptr]
    up = shoe[ptr + 1]
    p2 = shoe[ptr + 2]
    hole = shoe[ptr + 3]
    ptr += 4
    u = cval(up)
    rec[4] = start_cat(p1, p2)
    rec[5] = u
    pp_net = 0.0
    if spp > 0:
        k = pp_cat(p1, p2)
        rec[1] = k
        pp_net = spp * PP_MULT[k]
    fc_net = 0.0
    if sfc > 0:
        k = fc_cat_of_sum(fcval(p1) + fcval(p2) + fcval(up) + fcval(hole))
        rec[2] = k
        fc_net = sfc * FC_MULT[k]
    side_net = pp_net + fc_net

    dealer_bj = (u == 1 and cval(hole) == 10) or (u == 10 and cval(hole) == 1)
    player_bj = (cval(p1) + cval(p2) == 11) and (cval(p1) == 1 or cval(p2) == 1)
    peek = R[R_PEEK] == 1

    Vn = Vall[min(hidx + 1, Vall.shape[0] - 1)]
    offs = np.zeros(4)
    offp = np.zeros(4)
    inspay = np.zeros(7)
    stv = np.zeros((23, 2))
    hitv = np.zeros((23, 2))
    dblv = np.zeros((23, 2))
    best = np.zeros((23, 2))
    Du = D[u]

    # ---------------- insurance ----------------
    ins = 0.0
    if u == 1 and free >= b / 2.0:
        take = False
        if useopt:
            tens = 96.0 * NDECK / 6.0 - (1.0 if cval(p1) == 10 else 0.0) - (1.0 if cval(p2) == 10 else 0.0)
            pbj = tens / (52.0 * NDECK - 3.0)
            half = b / 2.0
            vals = np.zeros(2)
            for ti in range(2):
                ii = half if ti == 1 else 0.0
                if peek:
                    # dealer BJ branch: 4CT result is known exactly (hole = ten)
                    s4 = fcval(p1) + fcval(p2) + 11 + 10
                    fcbj = sfc * FC_MULT[fc_cat_of_sum(s4)] if sfc > 0 else 0.0
                    mainbj = 0.0 if player_bj else -b
                    vbj = vget(Vn, c + pp_net + fcbj + mainbj + 2.0 * ii)
                    nq = fc_mixture(p1, p2, up, R, offs, offp, c + pp_net - ii, sfc, 10)
                    if player_bj:
                        hv = 0.0
                        for q in range(nq):
                            hv += offp[q] * vget(Vn, offs[q] + 1.5 * b)
                    else:
                        for kk in range(7):
                            inspay[kk] = 0.0
                        hand_tables(Vn, offs, offp, nq, Du, inspay, b, stv, hitv, dblv, best)
                        hv = initial_best(p1, p2, u, b, free - ii, R, stv, hitv, dblv, best,
                                          Vn, offs, offp, nq, Du, inspay, splt, subd)
                    vals[ti] = pbj * vbj + (1.0 - pbj) * hv
                else:
                    nq = fc_mixture(p1, p2, up, R, offs, offp, c + pp_net, sfc, 0)
                    for kk in range(7):
                        inspay[kk] = -ii
                    inspay[6] = 2.0 * ii
                    if player_bj:
                        hv = 0.0
                        for q in range(nq):
                            hv += offp[q] * (pbj * vget(Vn, offs[q] + inspay[6]) +
                                             (1 - pbj) * vget(Vn, offs[q] + 1.5 * b - ii))
                        vals[ti] = hv
                    else:
                        hand_tables(Vn, offs, offp, nq, Du, inspay, b, stv, hitv, dblv, best)
                        vals[ti] = initial_best(p1, p2, u, b, free - ii, R, stv, hitv, dblv, best,
                                                Vn, offs, offp, nq, Du, inspay, splt, subd)
            take = vals[1] > vals[0] + 1e-12
        else:
            take = P[7] > 0.0 and np.random.random() < P[7]
        if take:
            ins = b / 2.0
            free -= ins
            rec[3] = 1.0
    ins_net = 0.0
    if ins > 0:
        ins_net = 2.0 * ins if dealer_bj else -ins

    # ---------------- immediate resolutions ----------------
    if dealer_bj and (peek or player_bj):
        main = 0.0 if player_bj else -b
        rec[0] = main / b
        rec[6] = 6.0
        return c + main + side_net + ins_net, ptr
    if player_bj:
        rec[0] = 1.5
        return c + 1.5 * b + side_net + ins_net, ptr

    # ---------------- optimizer tables for this hand ----------------
    if useopt:
        excl = 0
        if peek and u == 1:
            excl = 10
        elif peek and u == 10:
            excl = 1
        nq = fc_mixture(p1, p2, up, R, offs, offp, c + pp_net - (ins if peek else 0.0), sfc, excl)
        for kk in range(7):
            inspay[kk] = 0.0
        if (not peek) and ins > 0:
            for kk in range(7):
                inspay[kk] = -ins
            inspay[6] = 2.0 * ins
        hand_tables(Vn, offs, offp, nq, Du, inspay, b, stv, hitv, dblv, best)
    else:
        nq = 1

    # ---------------- player plays ----------------
    hh = np.zeros(2, dtype=np.int64)    # hard totals
    ha = np.zeros(2, dtype=np.int64)    # has ace
    hm = np.ones(2)                     # stake multiplier (2 if doubled)
    nh = 1
    hh[0] = cval(p1) + cval(p2)
    ha[0] = 1 if (cval(p1) == 1 or cval(p2) == 1) else 0

    pv = cval(p1) if is_pair(p1, p2, R) else 0
    can_split = pv > 0 and free >= b
    can_dbl = free >= b
    if useopt:
        act = initial_action(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                             Vn, offs, offp, nq, Du, inspay, splt, subd)
    else:
        act = decide_param(hh[0], ha[0], 2, pv, can_dbl, can_split, u, act2, actN, splt, P, R)

    if act == SPLIT:
        free -= b
        nh = 2
        aces = cval(p1) == 1
        firsts = np.array([p1, p2])
        for i in range(2):
            card = shoe[ptr]
            ptr += 1
            hh[i] = cval(firsts[i]) + cval(card)
            ha[i] = 1 if (cval(firsts[i]) == 1 or cval(card) == 1) else 0
            if aces:
                continue
            n = 2
            while True:
                dbl_ok = R[R_DAS] == 1 and free >= b
                if ptype == T_OPT:
                    a2 = decide_param(hh[i], ha[i], n, 0, dbl_ok, False, u, act2, actN, splt, ZP, R)
                else:
                    a2 = decide_param(hh[i], ha[i], n, 0, dbl_ok, False, u, act2, actN, splt, P, R)
                if a2 == STAND:
                    break
                card = shoe[ptr]
                ptr += 1
                hh[i] += cval(card)
                if cval(card) == 1:
                    ha[i] = 1
                n += 1
                if a2 == DOUBLE:
                    hm[i] = 2.0
                    free -= b
                    break
                if best_total(hh[i], ha[i]) >= 21:
                    break
    else:
        n = 2
        while True:
            if act == STAND:
                break
            card = shoe[ptr]
            ptr += 1
            hh[0] += cval(card)
            if cval(card) == 1:
                ha[0] = 1
            n += 1
            if act == DOUBLE:
                hm[0] = 2.0
                free -= b
                break
            if best_total(hh[0], ha[0]) >= 21:
                break
            if useopt:
                act = HIT if hitv[hh[0], ha[0]] > stv[hh[0], ha[0]] + 1e-12 else STAND
            else:
                act = decide_param(hh[0], ha[0], n, 0, False, False, u, act2, actN, splt, P, R)

    # ---------------- dealer ----------------
    alive = False
    for i in range(nh):
        if best_total(hh[i], ha[i]) <= 21:
            alive = True
    dh = cval(up) + cval(hole)
    da = 1 if (cval(up) == 1 or cval(hole) == 1) else 0
    if not dealer_bj and (alive or R[R_DRAWBUST] == 1):
        while best_total(dh, da) < 17:
            card = shoe[ptr]
            ptr += 1
            dh += cval(card)
            if cval(card) == 1:
                da = 1
    dt = best_total(dh, da)
    if dealer_bj:
        rec[6] = 6.0
    elif alive or R[R_DRAWBUST] == 1:
        rec[6] = 5.0 if dt > 21 else dt - 17.0
    else:
        rec[6] = 7.0      # dealer didn't play out (you busted)

    # ---------------- settle ----------------
    main = 0.0
    for i in range(nh):
        pt = best_total(hh[i], ha[i])
        stake = b * hm[i]
        if pt > 21:
            main -= stake
        elif dealer_bj:
            main -= stake
        elif dt > 21 or pt > dt:
            main += stake
        elif pt < dt:
            main -= stake
    rec[0] = main / b
    return c + main + side_net + ins_net, ptr


ZP = np.zeros(20)   # "no habits" parameter vector = pure basic strategy


@njit(cache=True)
def _option_values(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                   Vn, offs, offp, nq, Du, inspay, splt, subd, out):
    """out[0..3] = value of stand, hit, double, split (-inf if not allowed)."""
    h = cval(p1) + cval(p2)
    a = 1 if (cval(p1) == 1 or cval(p2) == 1) else 0
    out[0] = stv[h, a]
    out[1] = hitv[h, a] if best_total(h, a) < 21 else -1e18
    out[2] = dblv[h, a] if (free >= b and double_ok(h, a, R)) else -1e18
    out[3] = -1e18
    if is_pair(p1, p2, R) and free >= b:
        pv = cval(p1)
        das = 1 if (R[R_DAS] == 1 and free - b >= b) else 0
        out[3] = split_value(Vn, offs, offp, nq, Du, inspay, b, subd[das, pv, u])


@njit(cache=True)
def initial_action(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                   Vn, offs, offp, nq, Du, inspay, splt, subd):
    out = np.empty(4)
    _option_values(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                   Vn, offs, offp, nq, Du, inspay, splt, subd, out)
    bi = 0
    for i in range(1, 4):
        if out[i] > out[bi] + 1e-12:
            bi = i
    return bi


@njit(cache=True)
def initial_best(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                 Vn, offs, offp, nq, Du, inspay, splt, subd):
    out = np.empty(4)
    _option_values(p1, p2, u, b, free, R, stv, hitv, dblv, best,
                   Vn, offs, offp, nq, Du, inspay, splt, subd, out)
    return out.max()


# ----------------------------------------------------------------------------
# Shoe + match simulation
# ----------------------------------------------------------------------------
@njit(cache=True)
def make_shoe(shoe):
    n = 52 * NDECK
    for i in range(n):
        shoe[i] = i % 52
    for i in range(SHUF):     # partial Fisher-Yates: first SHUF positions are a uniform random draw
        j = i + int(np.random.random() * (n - i))
        t = shoe[i]
        shoe[i] = shoe[j]
        shoe[j] = t


@njit(cache=True)
def init_pstate(P, pst):
    """per-match random habits for parametric players: fixed bet, which hands to shove"""
    for i in range(6):
        pst[i] = 0.0
    nb = 0
    for i in range(6):
        if P[i] > 0:
            nb += 1
    if nb > 0:
        pst[0] = P[int(np.random.random() * nb)]
    na = int(P[14])
    if P[14] - na > 0 and np.random.random() < P[14] - na:
        na += 1
    na = min(na, 5)
    chosen = 0
    while chosen < na:
        k = int(np.random.random() * 5)
        if pst[1 + k] == 0.0:
            pst[1 + k] = 1.0
            chosen += 1


@njit(cache=True)
def play_match_player(shoe, ptype, P, R, D, act2, actN, splt, subd,
                      bet_tab, pp_tab, fc_tab, Vall, pst, rec, trace):
    """Tree mode (ptype T_OPT with P[19] == 1): bet_tab rows are result-history
    nodes (see corr.py) instead of hand numbers; the node advances by the class
    of each hand's result."""
    c = 1000.0
    ptr = 0
    if ptype == T_OPT:
        pst[0] = 1.0
        if P[12] > 0.0:
            pst[0] = 1.0 + P[12] * (2.0 * np.random.random() - 1.0)
    tree = ptype == T_OPT and P[19] == 1.0
    code = 0
    for h in range(5):
        row = NODE_OFF[h] + code if tree else h
        c, ptr = play_hand(shoe, ptr, c, row, ptype, P, pst, R, D, act2, actN, splt, subd,
                           bet_tab, pp_tab, fc_tab, Vall, rec)
        trace[h] = c
        k = obs_key(rec)
        trace[5 + h] = k
        if tree:
            # tree tables carry the observation -> class map in Vall[0] (Vall is unused in tree mode)
            code = code * NCLS + int(Vall[0, k])
    return c


# ---------------------------------------------------------------------------
# Result-history tree (correlation-aware plan, corr.py)
# ---------------------------------------------------------------------------
NCLS = 8
NODE_OFF = np.array([0, 1, 9, 73, 585, 4681, 37449])   # first node id at each depth (8 classes)
NSTART, NDCAT = 35, 8
NKEYS = NSTART * 10 * 6 * NDCAT                         # observation keys per hand


@njit(cache=True)
def start_cat(c1, c2):
    """Your starting hand: 0 blackjack, 1-10 pair (by value), 11-18 soft A2..A9, 19-33 hard 5..19."""
    v1, v2 = cval(c1), cval(c2)
    if (v1 == 1 and v2 == 10) or (v1 == 10 and v2 == 1):
        return 0
    if v1 == v2:
        return v1
    if v1 == 1 or v2 == 1:
        return 11 + (v1 + v2 - 1) - 2
    return 19 + (v1 + v2) - 5


@njit(cache=True)
def obs_key(rec):
    """What you saw on a hand: (start, upcard, your result class, dealer finish)."""
    return ((int(rec[4]) * 10 + (int(rec[5]) - 1)) * 6 + xclass(rec[0])) * NDCAT + int(rec[6])


@njit(cache=True)
def xclass(x):
    """Class of a hand result (net units of the main bet):
    0 lost 2+ (double/split), 1 lost, 2 push, 3 won 1, 4 blackjack, 5 won 2+."""
    if x <= -2.0:
        return 0
    if x < 0.0:
        return 1
    if x == 0.0:
        return 2
    if x == 1.5:
        return 4
    if x <= 1.0:
        return 3
    return 5


@njit(parallel=True, cache=True)
def gen_scenarios(n, seed, nchunks, tB, PB, R, D, act2, actN, splt, subd,
                  bet_b, pp_b, fc_b, Vall_b):
    """n matches on fresh shoes: 'me' plays basic strategy with a flat 10 bet
    (doubles always affordable) and records each hand's result in units; the
    opponent plays its own strategy on the SAME shoe.  Returns
    X[n,5] (my unit results), K[n,5] (what I saw each hand, see obs_key),
    O[n] (opp final chips), OT[n,5] (opp chips after each hand)."""
    X = np.zeros((n, 5), dtype=np.float32)
    K = np.zeros((n, 5), dtype=np.int32)
    O = np.zeros(n, dtype=np.float32)
    OT = np.zeros((n, 5), dtype=np.float32)
    per = (n + nchunks - 1) // nchunks
    PA = np.zeros(20)
    PA[0] = 10.0
    PA[6] = 1.0
    dummy = np.zeros((5, 1))
    for ch in prange(nchunks):
        np.random.seed(seed * 1000003 + ch)
        shoe = np.empty(52 * NDECK, dtype=np.int64)
        pa = np.zeros(6)
        pb = np.zeros(6)
        rec = np.zeros(8)
        tr = np.zeros(10)
        tro = np.zeros(10)
        lo = ch * per
        hi = min(n, lo + per)
        for i in range(lo, hi):
            make_shoe(shoe)
            init_pstate(PA, pa)
            init_pstate(PB, pb)
            play_match_player(shoe, T_PARAM, PA, R, D, act2, actN, splt, subd,
                              dummy, dummy, dummy, Vall_b, pa, rec, tr)
            prev = 1000.0
            for h in range(5):
                X[i, h] = (tr[h] - prev) / 10.0
                K[i, h] = int(tr[5 + h])
                prev = tr[h]
            O[i] = play_match_player(shoe, tB, PB, R, D, act2, actN, splt, subd,
                                     bet_b, pp_b, fc_b, Vall_b, pb, rec, tro)
            for h in range(5):
                OT[i, h] = tro[h]
    return X, K, O, OT


@njit(parallel=True, cache=True)
def simulate(n, seed, nchunks, tA, PA, tB, PB, R, D, act2, actN, splt, subd,
             bet_tab, pp_tab, fc_tab, Vall, nhist,
             bet_b, pp_b, fc_b, Vall_b):
    """Play n head-to-head matches (A vs B) from the same shoe each match.
    A uses plan tables (bet_tab, pp_tab, fc_tab, Vall); B uses (bet_b, pp_b, fc_b, Vall_b)
    (only relevant when a player is T_OPT). Returns per-chunk W/T/L counts for A
    and histograms of both players' final chips (bin = chips/2.5, last bin = overflow)."""
    wtl = np.zeros((nchunks, 3), dtype=np.int64)
    histA = np.zeros((nchunks, nhist), dtype=np.int64)
    histB = np.zeros((nchunks, nhist), dtype=np.int64)
    per = n // nchunks
    for ch in prange(nchunks):
        np.random.seed(seed * 1000003 + ch)
        shoe = np.empty(52 * NDECK, dtype=np.int64)
        pstA = np.zeros(6)
        pstB = np.zeros(6)
        rec = np.zeros(8)
        tr = np.zeros(10)
        m = per + (1 if ch < n - per * nchunks else 0)
        for _ in range(m):
            make_shoe(shoe)
            init_pstate(PA, pstA)
            init_pstate(PB, pstB)
            ca = play_match_player(shoe, tA, PA, R, D, act2, actN, splt, subd,
                                   bet_tab, pp_tab, fc_tab, Vall, pstA, rec, tr)
            cb = play_match_player(shoe, tB, PB, R, D, act2, actN, splt, subd,
                                   bet_b, pp_b, fc_b, Vall_b, pstB, rec, tr)
            if ca > cb:
                wtl[ch, 0] += 1
            elif ca == cb:
                wtl[ch, 1] += 1
            else:
                wtl[ch, 2] += 1
            ia = min(int(ca / CHIP + 0.5), nhist - 1)
            ib = min(int(cb / CHIP + 0.5), nhist - 1)
            histA[ch, ia] += 1
            histB[ch, ib] += 1
    return wtl, histA.sum(axis=0), histB.sum(axis=0)


@njit(parallel=True, cache=True)
def sample_hands(n, seed, nchunks, P, R, D, act2, actN, splt, subd, dummy_tab, Vall):
    """Joint distribution of (main result, PP category, FC category) for one hand of
    basic strategy with a 10 bet and both side stakes at 5. Main result index = 2*units + 10."""
    out = np.zeros((nchunks, 21, 4, 4), dtype=np.int64)
    per = n // nchunks
    for ch in prange(nchunks):
        np.random.seed(seed * 7919 + ch)
        shoe = np.empty(52 * NDECK, dtype=np.int64)
        pst = np.zeros(6)
        pst[0] = 10.0
        rec = np.zeros(8)
        for _ in range(per):
            make_shoe(shoe)
            play_hand(shoe, 0, P[19], 0, T_PARAM, P, pst, R, D, act2, actN, splt, subd,
                      dummy_tab, dummy_tab, dummy_tab, Vall, rec)
            mi = int(round(rec[0] * 2)) + 10
            out[ch, mi, int(rec[1]), int(rec[2])] += 1
    return out.sum(axis=0)


# ----------------------------------------------------------------------------
# Bet / side-stake dynamic program
# ----------------------------------------------------------------------------
@njit(cache=True)
def _main_options(c, out):
    n = 0
    x = 10.0
    while x <= c and x <= 100.0:
        out[n] = x
        n += 1
        x += 5.0
    x = 100.0
    while True:
        x = x * 1.12
        y = floor5(x)
        if y > c:
            break
        out[n] = y
        n += 1
    for f in (0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.75, 1.0):
        y = floor5(c * f)
        if y >= 10.0:
            out[n] = y
            n += 1
    return n


@njit(cache=True)
def _side_options(c, smin, smaxf, out):
    out[0] = 0.0
    n = 1
    smax = c * smaxf
    for s in (5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0):
        if s >= smin and s <= smax:
            out[n] = s
            n += 1
    for f in (0.5, 1.0):
        y = floor5(c * f * smaxf)
        if y >= smin and y > 1000.0:
            out[n] = y
            n += 1
    return n


@njit(parallel=True, cache=True)
def dp_step(Vnext, Wnext, Lnext, ncomp, jm_full, jp_full, jf_full, jw_full,
            jm_nx, jp_nx, jf_nx, jw_nx, minbet, smin, smaxf):
    """One backward DP step.  For each chip level choose (bet, PP stake, FC stake)
    maximizing E[Vnext].  j*_full: joint outcome table when doubles/splits are
    affordable; j*_nx: when they aren't.  Entries: main units, PP mult, FC mult, prob.
    Above ncomp the strategy is min bet (opponents are almost never that high)."""
    nv = Vnext.shape[0]
    V = Vnext.copy()
    W = Wnext.copy()
    L = Lnext.copy()
    bt = np.zeros(ncomp)
    pt = np.zeros(ncomp)
    ft = np.zeros(ncomp)
    for ci in prange(ncomp):
        c = ci * CHIP
        if c < minbet:
            continue
        mo = np.empty(200)
        so = np.empty(16)
        nm = _main_options(c, mo)
        ns = _side_options(c, smin, smaxf, so)
        bestv = -1e18
        bb = 10.0
        bp = 0.0
        bf = 0.0
        for i in range(nm):
            b = mo[i]
            for j in range(ns):
                s1 = so[j]
                for k in range(ns):
                    s2 = so[k]
                    if b + s1 + s2 > c:
                        continue
                    if c - b - s1 - s2 >= b:
                        jm = jm_full; jp = jp_full; jf = jf_full; jw = jw_full
                    else:
                        jm = jm_nx; jp = jp_nx; jf = jf_nx; jw = jw_nx
                    ev = 0.0
                    for e in range(jm.shape[0]):
                        x = c + jm[e] * b + jp[e] * s1 + jf[e] * s2
                        ix = int(x / CHIP + 0.5)
                        if ix >= nv:
                            ix = nv - 1
                        ev += jw[e] * Vnext[ix]
                    if ev > bestv + 1e-12:
                        bestv = ev
                        bb = b
                        bp = s1
                        bf = s2
        V[ci] = bestv
        bt[ci] = bb
        pt[ci] = bp
        ft[ci] = bf
        # policy evaluation of win / loss probability under the chosen action
        if c - bb - bp - bf >= bb:
            jm = jm_full; jp = jp_full; jf = jf_full; jw = jw_full
        else:
            jm = jm_nx; jp = jp_nx; jf = jf_nx; jw = jw_nx
        w = 0.0
        l = 0.0
        for e in range(jm.shape[0]):
            x = c + jm[e] * bb + jp[e] * bp + jf[e] * bf
            ix = int(x / CHIP + 0.5)
            if ix >= nv:
                ix = nv - 1
            w += jw[e] * Wnext[ix]
            l += jw[e] * Lnext[ix]
        W[ci] = w
        L[ci] = l
    return V, W, L, bt, pt, ft
