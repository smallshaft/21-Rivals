"""
Live advisor: the exact same decision logic the simulator uses (core.py), wrapped
for one-hand-at-a-time queries from the web app.

Cards are entered by rank only (1 = Ace, 10 = any ten/face). Suits only matter for
Perfect Pairs, which the user reports directly (mixed / colored / perfect).
"""
from __future__ import annotations

import threading

import numpy as np

from . import core
from .config import Settings, load_settings
from .optimizer import get_plan, Plan, NCOMP
from .strategy import build_tables, Tables, ACT_NAMES

PP_NAMES = {0: "none", 1: "mixed", 2: "colored", 3: "perfect"}


def card(rank: int) -> int:
    """rank 1..10 (10 = T/J/Q/K) -> an engine card id (suit irrelevant here)"""
    r = int(rank)
    if r >= 10:
        r = 10
    return (r - 1) * 4


class Advisor:
    def __init__(self, settings: Settings | None = None):
        self.lock = threading.Lock()
        self.load(settings or load_settings())

    def load(self, settings: Settings):
        T = build_tables(settings.rules)
        plan = get_plan(settings)
        with self.lock:
            self.settings, self.T, self.plan = settings, T, plan
        # warm up numba so the first real query is instant
        self.prehand(1, 1000)
        self.action({"hand": 1, "chips": 1000, "bet": 100, "pp": 0, "fc": 0,
                     "cards": [10, 6], "up": 1, "insurance": False})

    # ------------------------------------------------------------------
    def prehand(self, hand: int, chips: float) -> dict:
        h = int(hand) - 1
        c = float(chips)
        P = self.plan
        ci = int(round(c / core.CHIP))
        if c < 10:
            return {"bet": 0, "pp": 0, "fc": 0, "note": "Under 10 chips: you can't bet."}
        if ci < NCOMP:
            b, spp, sfc = P.bet[h, ci], P.pp[h, ci], P.fc[h, ci]
        else:
            b, spp, sfc = 10.0, 0.0, 0.0
        ci = min(ci, P.Wall.shape[1] - 1)
        win, loss = float(P.Wall[h, ci]), float(P.Lall[h, ci])
        return {"bet": float(b), "pp": float(spp), "fc": float(sfc), "win": win, "loss": loss,
                "tie": max(0.0, 1 - win - loss), "ev": float(P.Vall[h, ci]),
                "allin": bool(b >= core.floor5(c))}

    # ------------------------------------------------------------------
    def _context(self, st, ins_taken):
        """Build the expectimax tables for this hand: returns dict of arrays."""
        T, P = self.T, self.plan
        h = int(st["hand"]) - 1
        c = float(st["chips"]); b = float(st["bet"])
        spp = float(st.get("pp") or 0); sfc = float(st.get("fc") or 0)
        cards = [card(x) for x in st["cards"][:2]]
        up = card(st["up"]); u = core.cval(up)
        peek = T.R[core.R_PEEK] == 1
        pp_net = 0.0
        if spp > 0:
            is_pair = cards[0] // 4 == cards[1] // 4
            cat = int(st.get("pp_cat") or 0) if is_pair else 0
            pp_net = spp * core.PP_MULT[cat]
        ins = b / 2.0 if ins_taken else 0.0
        free = c - b - spp - sfc - ins
        excl = 10 if (peek and u == 1) else 1 if (peek and u == 10) else 0
        offs = np.zeros(4); offp = np.zeros(4); inspay = np.zeros(7)
        base = c + pp_net - (ins if peek else 0.0)
        nq = core.fc_mixture(cards[0], cards[1], up, T.R, offs, offp, base, sfc, excl)
        if (not peek) and ins > 0:
            inspay[:] = -ins
            inspay[6] = 2 * ins
        out = {}
        for name, V in (("v", P.Vall[h + 1]), ("w", P.Wall[h + 1])):
            stv = np.zeros((23, 2)); hitv = np.zeros((23, 2)); dblv = np.zeros((23, 2)); best = np.zeros((23, 2))
            core.hand_tables(V, offs, offp, nq, T.D[u], inspay, b, stv, hitv, dblv, best)
            out[name] = (V, stv, hitv, dblv, best)
        return dict(h=h, c=c, b=b, spp=spp, sfc=sfc, cards=cards, up=up, u=u, peek=peek,
                    pp_net=pp_net, ins=ins, free=free, offs=offs, offp=offp, nq=nq,
                    inspay=inspay, tabs=out)

    def insurance(self, st) -> dict:
        """Should we insure? Mirrors the logic in core.play_hand."""
        T, P = self.T, self.plan
        h = int(st["hand"]) - 1
        c = float(st["chips"]); b = float(st["bet"])
        spp = float(st.get("pp") or 0); sfc = float(st.get("fc") or 0)
        p1, p2 = (card(x) for x in st["cards"][:2])
        up = card(st["up"])
        free = c - b - spp - sfc
        if core.cval(up) != 1 or free < b / 2:
            return {"offered": False}
        Vn = P.Vall[h + 1]
        peek = T.R[core.R_PEEK] == 1
        ctx0 = self._context(st, False)
        pp_net = ctx0["pp_net"]
        tens = 96.0 - (core.cval(p1) == 10) - (core.cval(p2) == 10)
        pbj = tens / 309.0
        player_bj = {core.cval(p1), core.cval(p2)} == {1, 10}
        vals = []
        for take in (False, True):
            ii = b / 2 if take else 0.0
            ctx = self._context(st, take)
            V, stv, hitv, dblv, best = ctx["tabs"]["v"]
            if peek:
                s4 = core.fcval(p1) + core.fcval(p2) + 21
                fcbj = sfc * core.FC_MULT[core.fc_cat_of_sum(s4)] if sfc > 0 else 0.0
                vbj = core.vget(Vn, c + pp_net + fcbj + (0.0 if player_bj else -b) + 2 * ii)
                if player_bj:
                    hv = sum(ctx["offp"][q] * core.vget(Vn, ctx["offs"][q] + 1.5 * b) for q in range(ctx["nq"]))
                else:
                    hv = core.initial_best(p1, p2, 1, b, free - ii, T.R, stv, hitv, dblv, best, Vn,
                                           ctx["offs"], ctx["offp"], ctx["nq"], T.D[1], ctx["inspay"],
                                           T.splt, T.subd)
                vals.append(pbj * vbj + (1 - pbj) * hv)
            else:
                if player_bj:
                    vals.append(sum(ctx["offp"][q] * (pbj * core.vget(Vn, ctx["offs"][q] + 2 * ii) +
                                    (1 - pbj) * core.vget(Vn, ctx["offs"][q] + 1.5 * b - ii))
                                    for q in range(ctx["nq"])))
                else:
                    vals.append(core.initial_best(p1, p2, 1, b, free - ii, T.R, stv, hitv, dblv, best, Vn,
                                                  ctx["offs"], ctx["offp"], ctx["nq"], T.D[1], ctx["inspay"],
                                                  T.splt, T.subd))
        return {"offered": True, "take": bool(vals[1] > vals[0] + 1e-12),
                "ev_no": float(vals[0]), "ev_yes": float(vals[1]), "p_dealer_bj": pbj}

    # ------------------------------------------------------------------
    def action(self, st) -> dict:
        """st: hand, chips, bet, pp, fc, pp_cat, cards (main hand ranks, in order),
        up, insurance (bool), split (bool), sub ([[ranks],[ranks]]), sub_doubled ([bool,bool]),
        active (0/1 split hand index).  Returns the recommended action for the active hand."""
        with self.lock:
            return self._action(st)

    def _action(self, st):
        T = self.T
        ctx = self._context(st, bool(st.get("insurance")))
        b, free, u = ctx["b"], ctx["free"], ctx["u"]
        if st.get("split"):
            # split sub-hands are played by basic strategy (same as the simulator)
            i = int(st.get("active", 0))
            sub = [card(x) for x in st["sub"][i]]
            doubled = st.get("sub_doubled", [False, False])
            free2 = free - b - b * sum(1 for d in doubled if d)
            hh = sum(core.cval(x) for x in sub)
            ha = 1 if any(core.cval(x) == 1 for x in sub) else 0
            t = core.best_total(hh, ha)
            if core.cval(sub[0]) == 1 and len(sub) >= 2:
                return {"action": "DONE", "why": "Split aces get one card each.", "total": t}
            if t > 21:
                return {"action": "BUST", "total": t}
            if t == 21:
                return {"action": "STAND", "total": t, "why": "21"}
            dbl_ok = T.R[core.R_DAS] == 1 and free2 >= b and len(sub) == 2
            a = core.decide_param(hh, ha, len(sub), 0, dbl_ok, False, u, T.act2, T.actN, T.splt,
                                  core.ZP, T.R)
            return {"action": ACT_NAMES[int(a)], "total": t, "soft": bool(ha and hh + 10 <= 21),
                    "why": "split hand: basic strategy"}

        cards = [card(x) for x in st["cards"]]
        hh = sum(core.cval(x) for x in cards)
        ha = 1 if any(core.cval(x) == 1 for x in cards) else 0
        t = core.best_total(hh, ha)
        soft = bool(ha and hh + 10 <= 21)
        if len(cards) == 2 and t == 21:
            return {"action": "BLACKJACK", "total": 21}
        if t > 21:
            return {"action": "BUST", "total": t}
        if t == 21:
            return {"action": "STAND", "total": 21, "why": "21"}
        res = {"total": t, "soft": soft}
        V, stv, hitv, dblv, best = ctx["tabs"]["v"]
        W, wstv, whitv, wdblv, wbest = ctx["tabs"]["w"]
        if len(cards) == 2:
            out = np.empty(4); wout = np.empty(4)
            args = (ctx["offs"], ctx["offp"], ctx["nq"], T.D[u], ctx["inspay"], T.splt, T.subd)
            core._option_values(cards[0], cards[1], u, b, free, T.R, stv, hitv, dblv, best, V, *args, out)
            core._option_values(cards[0], cards[1], u, b, free, T.R, wstv, whitv, wdblv, wbest, W, *args, wout)
            bi = 0
            for i in range(1, 4):
                if out[i] > out[bi] + 1e-12:
                    bi = i
            opts = {ACT_NAMES[i]: {"ev": float(out[i]), "win": float(wout[i])}
                    for i in range(4) if out[i] > -1e17}
        else:
            opts = {"STAND": {"ev": float(stv[hh, ha]), "win": float(wstv[hh, ha])},
                    "HIT": {"ev": float(hitv[hh, ha]), "win": float(whitv[hh, ha])}}
            bi = core.HIT if hitv[hh, ha] > stv[hh, ha] + 1e-12 else core.STAND
        res["action"] = ACT_NAMES[bi]
        res["options"] = opts
        evs = sorted((v["ev"] for v in opts.values()), reverse=True)
        res["tossup"] = len(evs) > 1 and evs[0] - evs[1] < 0.002
        # flag deviations from chip-EV basic strategy
        pv = core.cval(cards[0]) if (len(cards) == 2 and core.is_pair(cards[0], cards[1], T.R)) else 0
        basic = core.decide_param(hh, ha, len(cards), pv, free >= b and len(cards) == 2,
                                  pv > 0 and free >= b, u, T.act2, T.actN, T.splt, core.ZP, T.R)
        res["basic"] = ACT_NAMES[int(basic)]
        if len(cards) == 2 and free < b and core.double_ok(hh, ha, T.R) and T.act2[hh, ha, u] == core.DOUBLE:
            res["why"] = "can't double: not enough chips left behind the bet"
        res["deviation"] = res["basic"] != res["action"]
        return res


_ADV = None


def get_advisor() -> Advisor:
    global _ADV
    if _ADV is None:
        _ADV = Advisor()
    return _ADV
