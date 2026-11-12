"""
One-page printable cheat sheet (results/cheatsheet.pdf) for the v2 plan.

The app's bet depends on your whole result history this match. Paper can't
hold that, so the sheet compresses it to (hand, your LAST result, your chips).
The compressed sheet is itself simulated, and its win rate is printed on it,
so you can see what it costs versus using the app.

    python -m rivals.cheatsheet
"""
from __future__ import annotations

import os

import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

from . import core
from . import corr
from . import optimizer as O
from .config import RESULTS_DIR, load_settings
from .strategy import build_tables
from .validate import summarize, mixture

UPS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]
UPL = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]
COL = {"H": colors.HexColor("#ffffff"), "S": colors.HexColor("#d9d9d4"),
       "D": colors.HexColor("#f6c48e"), "P": colors.HexColor("#c8b4ec")}
ROWS = [600, 750, 850, 900, 950, 970, 980, 990, 995, 1000, 1005, 1010, 1015, 1020, 1030, 1050, 1075,
        1100, 1150, 1250, 1400]
GROUPS = ["Lost", "Push", "Won", "BJ / won 2+"]   # = bucket ids 0..3 of the 'result' plan


def sheet_table(tp):
    """table[d, g, r] = bet for hand d+1 (d=1..4), last-result group g, chip row r
    (count-weighted median of the full plan's bets over matching histories)."""
    tab = np.zeros((5, len(GROUPS), len(ROWS)))
    for d in range(1, 5):
        for g in range(len(GROUPS)):
            nodes = [corr.OFF[d] + code for code in range(corr.NCLS ** d)
                     if code % corr.NCLS == g and tp.count[corr.OFF[d] + code] > 0]
            w = tp.count[nodes].astype(float)
            for r, chips in enumerate(ROWS):
                b = tp.bet[nodes, int(chips / core.CHIP)].astype(float)
                o = np.argsort(b)
                cw = np.cumsum(w[o]) / w.sum()
                tab[d, g, r] = b[o][np.searchsorted(cw, 0.5)]
    return tab


def sheet_policy(tp, tab):
    """Expand the printed table into an engine tree table: use the row at or below your chips."""
    B = tp.bet.astype(np.float64).copy()
    rows = np.array(ROWS, float)
    cgrid = np.arange(corr.NC) * core.CHIP
    ridx = np.clip(np.searchsorted(rows, cgrid, side="right") - 1, 0, len(ROWS) - 1)
    for d in range(1, 5):
        for code in range(corr.NCLS ** d):
            nd = corr.OFF[d] + code
            g = min(code % corr.NCLS, len(GROUPS) - 1)
            b = tab[d, g, ridx]
            b = np.minimum(b, 5.0 * np.floor(cgrid / 5.0 + 1e-9))
            B[nd] = np.maximum(b, 10.0)
    return B


def evaluate(tabs, s, T, n=1_000_000):
    P = corr.tree_player_params()
    per = {}
    for i, k in enumerate(["sharp_a", "casual_a", "casual_b"]):
        w, _, _ = core.simulate(n, 4242 + i, O.NCHUNK, core.T_OPT, P, core.T_PARAM, s.profile(k).as_params(),
                                T.R, T.D, T.act2, T.actN, T.splt, T.subd, *tabs, O.NV,
                                *O.dummy_plan_arrays())
        per[k] = summarize(*map(int, w.sum(axis=0)))
    return mixture(per, {k: s.mix.get(k, 0) for k in per})


def basic_letter(T, h, a, u, pair=0):
    if pair and T.splt[pair, u]:
        return "P"
    if core.double_ok(h, a, T.R):
        return {0: "S", 1: "H", 2: "D"}[int(T.act2[h, a, u])]
    return {0: "S", 1: "H"}[int(T.actN[h, a, u])]


def build(path=None):
    path = path or os.path.join(RESULTS_DIR, "cheatsheet.pdf")
    s = load_settings()
    T = build_tables(s.rules)
    app = corr.get_tree_plan(s, verbose=False)                       # what the app uses
    tp = corr.get_tree_plan(s, verbose=False, bucket_mode="result")  # result-only version for paper
    tab = sheet_table(tp)
    full = evaluate(app.engine_tables(), s, T)
    Bs = sheet_policy(tp, tab)
    sheet = evaluate((Bs, Bs, Bs, tp.engine_tables()[3]), s, T)
    b0 = float(tp.bet[0, 400])

    W, H = landscape(letter)
    c = canvas.Canvas(path, pagesize=(W, H))
    m = 22
    c.setFont("Helvetica-Bold", 14)
    c.drawString(m, H - m - 6, "21 Rivals cheat sheet")
    c.setFont("Helvetica", 7.5)
    c.drawString(m + 150, H - m - 6,
                 "Mix: " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in s.mix.items() if v > 0)
                 + f".  Dealer peeks: {s.rules.dealer_peeks}.  Reprint if settings change.")

    y = H - m - 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m, y, f"HAND 1: bet {b0:.0f}.   Every hand: no insurance, no side stakes, play the chart.")
    y -= 13
    c.setFont("Helvetica", 7.6)
    c.drawString(m, y, "Hands 2-5: find the table for the hand, the column for how your LAST hand went, "
                       "and the row at or BELOW your current chips.")
    y -= 10
    c.drawString(m, y, "Why: you both get the same cards. Lose a small bet -> they probably lost more, stay small. "
                       "Win -> they probably won more, bet up.")

    # four bet tables, 2 x 2
    cw0, cwi, rh = 40, 50, 10.2
    tw = cw0 + cwi * len(GROUPS)
    y0 = y - 16
    for i, d in enumerate(range(1, 5)):
        x = m + (i % 2) * (tw + 16)
        yy = y0 - (i // 2) * (rh * (len(ROWS) + 2) + 14)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, yy, f"HAND {d + 1}")
        yy -= rh
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x, yy, "Chips")
        for g, name in enumerate(GROUPS):
            c.drawString(x + cw0 + g * cwi, yy, name)
        c.setFont("Helvetica", 7.6)
        for r, chips in enumerate(ROWS):
            yy -= rh
            if r % 2 == 0:
                c.setFillColor(colors.HexColor("#efefea"))
                c.rect(x - 2, yy - 3, tw, rh, stroke=0, fill=1)
                c.setFillColor(colors.black)
            c.drawString(x, yy, f"{chips:,}" + ("+" if r == len(ROWS) - 1 else ""))
            for g in range(len(GROUPS)):
                c.drawString(x + cw0 + g * cwi, yy, f"{tab[d, g, r]:.0f}")
    yb = y0 - 2 * (rh * (len(ROWS) + 2) + 14) - 2
    c.setFont("Helvetica-Oblique", 6.8)
    c.drawString(m, yb, "Below 600 chips use the 600 row. Never bet more than you have. Bets are the main bet only.")

    # basic strategy chart
    bx, by0 = m + 2 * (tw + 16) + 6, H - m - 76
    c.setFont("Helvetica-Bold", 9)
    c.drawString(bx, by0, "BASIC STRATEGY (every hand)")
    cw, ch = 15.5, 11.2
    yy = by0 - 12
    c.setFont("Helvetica-Bold", 7)
    for j, ul in enumerate(UPL):
        c.drawCentredString(bx + 28 + j * cw + cw / 2, yy, ul)
    yy -= ch + 1

    def row(label, cells, yy):
        c.setFont("Helvetica", 7.3)
        c.drawString(bx, yy + 2.8, label)
        for j, L in enumerate(cells):
            c.setFillColor(COL[L])
            c.rect(bx + 28 + j * cw, yy, cw, ch, stroke=1, fill=1)
            c.setFillColor(colors.black)
            c.drawCentredString(bx + 28 + j * cw + cw / 2, yy + 2.8, L)

    for t in range(8, 18):
        row(f"{t}", [basic_letter(T, t, 0, u) for u in UPS], yy)
        yy -= ch
    yy -= 3
    for x in range(2, 9):
        row(f"A,{x}", [basic_letter(T, 1 + x, 1, u) for u in UPS], yy)
        yy -= ch
    yy -= 3
    for pv in [1, 2, 3, 4, 6, 7, 8, 9]:
        row("A,A" if pv == 1 else f"{pv},{pv}", [basic_letter(T, 2 * pv, 1 if pv == 1 else 0, u, pv) for u in UPS], yy)
        yy -= ch
    c.setFont("Helvetica", 7)
    yy -= 6
    for line in ["H hit  S stand  D double (9-11 only)  P split", "5,5 = play as 10.  T,T never split.  18+ stand.",
                 "Split hands: play by this chart."]:
        c.drawString(bx, yy, line)
        yy -= 9
    yy -= 6
    c.setFont("Helvetica-Bold", 8)
    c.drawString(bx, yy, "SIMULATED (win % of decided, break-even 55.56%)")
    yy -= 11
    c.setFont("Helvetica", 7.6)
    for line in [f"Using the app:        {100 * full['dec_rate']:.1f}%",
                 f"Using this sheet:     {100 * sheet['dec_rate']:.1f}%",
                 "vs the assumed mix of opponents. Against players",
                 "who also size bets to win the match, ~50%: a loser.",
                 "Log every match in the app to check reality."]:
        c.drawString(bx, yy, line)
        yy -= 9.5
    c.setFont("Helvetica-Oblique", 6)
    c.drawString(m, 12, "6-minute clock: don't overthink. Timing out forfeits. Odds are simulation estimates, not guarantees.")
    c.showPage()
    c.save()
    return path, full, sheet


if __name__ == "__main__":
    p, f, sh = build()
    print(p, f"app {f['dec_rate']:.4f}  sheet {sh['dec_rate']:.4f}")
