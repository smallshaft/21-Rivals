"""
Live advisor used by the web app (v2, correlation-aware).

Before each hand you give it the hand number, your chips, and what happened on
the previous hands of this match: your two cards, the dealer's upcard, your
result and how the dealer finished (the app records these as you play).
Because you both got the same cards, that tells it a lot about your opponent:
a 20 vs 6 that won on a dealer bust almost surely won for them too; a 16 vs 10
is a coin flip, since many players hit it.

In-hand play is basic strategy (the same play the plan was optimized and
validated with). Cards are entered by rank: 1 = Ace, 10 = any ten/face.
"""
from __future__ import annotations

import threading

import numpy as np

from . import core
from .config import Settings, load_settings, MODEL_NAMES
from .corr import get_tree_plan, TreePlan, node_id, history_code, NC, BUCKET_NAMES
from .strategy import build_tables, ACT_NAMES


def card(rank: int) -> int:
    r = min(int(rank), 10)
    return (r - 1) * 4


def result_units(chips_before, chips_after, bet):
    """Your result on a hand in units of the main bet (no side stakes in v2)."""
    if not bet:
        return 0.0
    x = (float(chips_after) - float(chips_before)) / float(bet)
    # snap to the nearest possible result (half units)
    return float(np.clip(round(x * 2) / 2, -4, 4))


class Advisor:
    def __init__(self, settings: Settings | None = None):
        self.lock = threading.Lock()
        self.load(settings or load_settings())

    def load(self, settings: Settings):
        T = build_tables(settings.rules)
        tp = get_tree_plan(settings)
        with self.lock:
            self.settings, self.T, self.tp = settings, T, tp
        self.prehand(1, 1000, [])
        self.prehand(2, 1010, [{"x": 1, "dealer": 5, "cards": [10, 10], "up": 6}])
        self.action({"hand": 1, "chips": 1000, "bet": 10, "cards": [10, 6], "up": 10})

    # ------------------------------------------------------------------
    def prehand(self, hand: int, chips: float, history=None) -> dict:
        """history: one entry per finished hand this match:
        {"x": result in units of your bet, "dealer": 0..7 (17,18,19,20,21,bust,BJ,didn't play out),
         "cards": [r1, r2] or None, "up": rank or None}"""
        tp = self.tp
        d = int(hand) - 1
        history = list(history or [])
        note = None
        if len(history) != d:
            note = (f"Results for {d} earlier hand(s) are needed for the best bet; got {len(history)}. "
                    "Missing ones were treated as pushes.")
            history = (history + [{"x": 0, "dealer": 3}] * d)[:d]
        buckets = [tp.bucket(hh.get("cards"), hh.get("up"), float(hh.get("x", 0)), int(hh.get("dealer", 7)))
                   for hh in history]
        nd = node_id(d, history_code(buckets))
        c = float(chips)
        if c < 10:
            return {"bet": 0, "note": "Under 10 chips: you can't bet."}
        ci = int(round(c / core.CHIP))
        b = float(tp.bet[nd, ci]) if ci < NC else 10.0
        cj = min(ci, NC - 1)
        win, loss = float(tp.W[nd, cj]), float(tp.L[nd, cj])
        q = tp.opp_q[nd]
        last = tp.opp_last[nd]
        opp = {"q10": q[0], "q25": q[1], "median": q[2], "q75": q[3], "q90": q[4],
               "last_up": float(last[0]), "last_same": float(last[1]), "last_down": float(last[2]),
               "history": [BUCKET_NAMES[bk] for bk in buckets], "scenarios": int(tp.count[nd])}
        if history:
            hh = history[-1]
            st = tp.hand_stat(hh.get("cards"), hh.get("up"), float(hh.get("x", 0)), int(hh.get("dealer", 7)))
            opp["last_insync"] = {"up": float(st[0]), "same": float(st[1]), "down": float(st[2])}
        return {"bet": b, "pp": 0.0, "fc": 0.0, "win": win, "loss": loss,
                "tie": max(0.0, 1 - win - loss), "allin": bool(b >= core.floor5(c)),
                "opponent": opp, "note": note}

    def insurance(self, st) -> dict:
        free = float(st["chips"]) - float(st["bet"])
        offered = int(st.get("up", 0)) == 1 and free >= float(st["bet"]) / 2
        return {"offered": offered, "take": False,
                "why": "Never: insurance costs ~7% and changing decisions breaks the shared-cards link the bet plan relies on."}

    # ------------------------------------------------------------------
    def action(self, st) -> dict:
        with self.lock:
            return self._action(st)

    def _action(self, st):
        T = self.T
        b = float(st["bet"])
        free = float(st["chips"]) - b
        u = core.cval(card(st["up"]))
        if st.get("split"):
            i = int(st.get("active", 0))
            sub = [card(x) for x in st["sub"][i]]
            doubled = st.get("sub_doubled", [False, False])
            free2 = free - b - b * sum(1 for x in doubled if x)
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
            return {"action": ACT_NAMES[int(a)], "total": t, "soft": bool(ha and hh + 10 <= 21)}

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
        pv = core.cval(cards[0]) if (len(cards) == 2 and core.is_pair(cards[0], cards[1], T.R)) else 0
        a = core.decide_param(hh, ha, len(cards), pv, free >= b and len(cards) == 2,
                              pv > 0 and free >= b, u, T.act2, T.actN, T.splt, core.ZP, T.R)
        res = {"action": ACT_NAMES[int(a)], "total": t, "soft": soft}
        if (len(cards) == 2 and free < b and core.double_ok(hh, ha, T.R)
                and T.act2[hh, ha, u] == core.DOUBLE):
            res["why"] = "can't double: not enough chips behind the bet"
        return res


_ADV = None


def get_advisor() -> Advisor:
    global _ADV
    if _ADV is None:
        _ADV = Advisor()
    return _ADV
