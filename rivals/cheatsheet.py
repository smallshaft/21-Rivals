"""
One-page printable cheat sheet (results/cheatsheet.pdf), generated from the
current strategy so it always matches the app.

    python -m rivals.cheatsheet
"""
from __future__ import annotations

import json
import os

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from .advisor import Advisor
from .config import RESULTS_DIR, load_settings
from . import core

UPS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]
UPL = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]
COL = {"H": colors.HexColor("#ffffff"), "S": colors.HexColor("#d9d9d4"),
       "D": colors.HexColor("#f6c48e"), "P": colors.HexColor("#c8b4ec")}
TWO = {8: [5, 3], 9: [5, 4], 10: [6, 4], 11: [6, 5], 12: [10, 2], 13: [10, 3], 14: [10, 4],
       15: [10, 5], 16: [10, 6], 17: [10, 7]}
HANDS = {**{str(k): v for k, v in TWO.items()},
         **{f"A{x}": [1, x] for x in range(2, 9)},
         **{("TT" if x == 10 else "AA" if x == 1 else f"{x}{x}"): [x, x] for x in [1, 2, 3, 4, 6, 7, 8, 9, 10]}}


def basic_letter(T, h, a, u, pair=0):
    if pair and T.splt[pair, u]:
        return "P"
    if core.double_ok(h, a, T.R):
        return {0: "S", 1: "H", 2: "D"}[int(T.act2[h, a, u])]
    return {0: "S", 1: "H"}[int(T.actN[h, a, u])]


def deviations(A: Advisor, hand, chips):
    r = A.prehand(hand, chips)
    out = []
    for name, cards in HANDS.items():
        for up, ul in zip(UPS, UPL):
            a = A.action({"hand": hand, "chips": chips, "bet": r["bet"], "pp": r["pp"], "fc": r["fc"],
                          "cards": cards, "up": up})
            if a.get("deviation"):
                out.append((name, ul, a["action"][0], a["basic"][0]))
    return r, out


def group(devs):
    """'9 v3-6: H' style compression."""
    by = {}
    for name, ul, act, basic in devs:
        by.setdefault((name, act), []).append(ul)
    parts = []
    for (name, act), ups in by.items():
        parts.append(f"{name} v{','.join(ups)}: {'Hit' if act == 'H' else 'Stand' if act == 'S' else act}")
    return parts


def build(path=None):
    path = path or os.path.join(RESULTS_DIR, "cheatsheet.pdf")
    A = Advisor()
    T = A.T
    rep = None
    rp = os.path.join(RESULTS_DIR, "report.json")
    if os.path.exists(rp):
        with open(rp) as f:
            rep = json.load(f)

    W, H = landscape(letter)
    c = canvas.Canvas(path, pagesize=(W, H))
    m = 22
    c.setFont("Helvetica-Bold", 14)
    c.drawString(m, H - m - 6, "21 Rivals cheat sheet")
    c.setFont("Helvetica", 7.5)
    s = load_settings()
    c.drawString(m + 150, H - m - 6,
                 f"Strategy optimized for mix: " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in s.mix.items() if v > 0)
                 + ".  Dealer peeks: %s.  Generated from the app; reprint if settings change." % s.rules.dealer_peeks)

    # ---------------- betting plan ----------------
    x0, y = m, H - m - 26
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y, "BET PLAN  (main bet  +PP = Perfect Pairs, +4C = 4-Card Total)")
    r1 = A.prehand(1, 1000)
    y -= 11
    c.setFont("Helvetica", 7.5)
    c.drawString(x0, y, f"Hand 1 (1,000 chips): bet {r1['bet']:.0f}"
                 + (f" +PP{r1['pp']:.0f}" if r1["pp"] else "") + (f" +4C{r1['fc']:.0f}" if r1["fc"] else ""))
    y -= 10
    levels = [200, 300, 400, 500, 600, 700, 800, 850, 900, 950, 975, 1000, 1025, 1050, 1100, 1150,
              1200, 1250, 1300, 1400, 1500, 1750, 2000, 2500]
    colw = [42, 82, 82, 82, 92]
    c.setFont("Helvetica-Bold", 7.5)
    hx = x0
    for i, t in enumerate(["Chips", "Hand 2", "Hand 3", "Hand 4", "Hand 5"]):
        c.drawString(hx, y, t)
        hx += colw[i]
    y -= 2
    c.setFont("Helvetica", 8.6)
    for lv in levels:
        y -= 13.5
        if levels.index(lv) % 2 == 0:
            c.setFillColor(colors.HexColor("#efefea"))
            c.rect(x0 - 2, y - 3.5, sum(colw), 13.5, stroke=0, fill=1)
            c.setFillColor(colors.black)
        hx = x0
        c.drawString(hx, y, f"{lv:,}" + ("+" if lv == levels[-1] else ""))
        hx += colw[0]
        for h in range(2, 6):
            r = A.prehand(h, lv)
            txt = f"{r['bet']:.0f}" + (" ALL" if r.get("allin") else "")
            if r["pp"]:
                txt += f" +PP{r['pp']:.0f}"
            if r["fc"]:
                txt += f" +4C{r['fc']:.0f}"
            c.drawString(hx, y, txt)
            hx += colw[h - 1]
    y -= 10
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawString(x0, y, "Between rows: use the nearer row. Chips are what you have BEFORE the hand. Above 2,500: bet 10.")
    y -= 8
    c.drawString(x0, y, "Pattern: bet big early, lock in a lead with minimum bets; when behind late, go big and add side stakes.")
    y -= 4

    # ---------------- basic strategy chart ----------------
    bx, by0 = x0 + sum(colw) + 18, H - m - 26
    c.setFont("Helvetica-Bold", 9)
    c.drawString(bx, by0, "BASIC STRATEGY (default play)")
    cw, ch = 17, 12.5
    yy = by0 - 12

    def header(yy):
        c.setFont("Helvetica-Bold", 8)
        for j, ul in enumerate(UPL):
            c.drawCentredString(bx + 28 + j * cw + cw / 2, yy, ul)

    def row(label, cells, yy):
        c.setFont("Helvetica", 8)
        c.drawString(bx, yy + 3, label)
        for j, L in enumerate(cells):
            c.setFillColor(COL[L])
            c.rect(bx + 28 + j * cw, yy, cw, ch, stroke=1, fill=1)
            c.setFillColor(colors.black)
            c.drawCentredString(bx + 28 + j * cw + cw / 2, yy + 3.2, L)

    header(yy)
    yy -= ch + 1
    for t in range(8, 18):
        row(f"{t}", [basic_letter(T, t, 0, u) for u in UPS], yy)
        yy -= ch
    yy -= 3
    for x in range(2, 9):
        row(f"A,{x}", [basic_letter(T, 1 + x, 1, u) for u in UPS], yy)
        yy -= ch
    yy -= 3
    for pv in [1, 2, 3, 4, 6, 7, 8, 9]:
        lab = "A,A" if pv == 1 else f"{pv},{pv}"
        row(lab, [basic_letter(T, 2 * pv, 1 if pv == 1 else 0, u, pv) for u in UPS], yy)
        yy -= ch
    c.setFont("Helvetica", 7.5)
    yy -= 4
    c.drawString(bx, yy, "H hit  S stand  D double (9-11 only)  P split.")
    yy -= 9
    c.drawString(bx, yy, "5,5 = play as 10. T,T never split. 18+ stand.")
    yy -= 9
    c.drawString(bx, yy, "Split hands: play by this chart.")

    # ---------------- deviations + insurance ----------------
    dx = bx + 28 + 10 * cw + 16
    dw = W - m - dx
    yd = H - m - 26
    c.setFont("Helvetica-Bold", 9)
    c.drawString(dx, yd, "KEY NUMBERS")
    yd -= 11

    def para(text, yd, size=7.4, bold=False, maxw=None):
        maxw = maxw or dw
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        words = text.split()
        line = ""
        for wd in words:
            t = (line + " " + wd).strip()
            if c.stringWidth(t, "Helvetica-Bold" if bold else "Helvetica", size) > (maxw or dw):
                c.drawString(dx, yd, line)
                yd -= size + 1.6
                line = wd
            else:
                line = t
        if line:
            c.drawString(dx, yd, line)
            yd -= size + 1.6
        return yd

    if rep:
        from .validate import mixture
        w = {**s.mix, "sharp_b": 0.0}      # mirror matches are ties either way; exclude
        o = mixture(rep["main"]["optimizer"], w)["dec_rate"]
        bp = mixture(rep["main"]["opt_basic_play"], w)["dec_rate"]
        diff = 100 * (o - bp)
        yd = para(f"Measured value of ALL in-hand deviations combined (sim, non-mirror opponents): {diff:+.2f} "
                  f"points of win rate. "
                  + ("That's basically nothing: the edge is the BET PLAN. If rushed, just play the chart."
                     if abs(diff) < 0.5 else ""), yd, bold=True)
        yd -= 2
    # deviation scenarios go under the bet plan (left column, wide)
    yr = yd
    yd = y - 22
    dx_saved, dw_saved = dx, dw
    dx, dw = x0, sum(colw)
    yd = para("MATCH DEVIATIONS (what the app plays differently from the chart, typical spots)", yd, size=9, bold=True)
    yd -= 1
    scen = [(1, 1000, "Hand 1 (and any time you're near 1,000 with a big bet out)"),
            (2, 1300, "Ahead (~1,300) with a small bet"),
            (5, 700, "Hand 5, behind, big bet"),
            (5, 1150, "Hand 5, slightly ahead")]
    for h, chips, title in scen:
        r, devs = deviations(A, h, chips)
        yd = para(f"{title}: bet {r['bet']:.0f}", yd, bold=True)
        g = group(devs)
        yd = para("; ".join(g) if g else "none - play the chart.", yd)
        yd -= 2
    dx, dw = dx_saved, dw_saved
    yd = yr
    yd = para("Rule of thumb: when a big bet is out and you're near the middle, the app avoids extra risk "
              "(skips some doubles and small-pair splits). When behind late it takes extra risk.", yd)
    yd -= 3
    # insurance scan
    takes = 0
    tot = 0
    for h in range(1, 6):
        for chips in [500, 800, 1000, 1200, 1500]:
            r = A.prehand(h, chips)
            for cards in ([10, 7], [10, 6], [9, 9], [10, 10], [5, 6]):
                ins = A.insurance({"hand": h, "chips": chips, "bet": r["bet"], "pp": r["pp"], "fc": r["fc"],
                                   "cards": cards, "up": 1})
                if ins.get("offered"):
                    tot += 1
                    takes += bool(ins["take"])
    yd = para(f"INSURANCE: the app recommends it in {takes} of {tot} sampled spots. "
              "Without the app: never take insurance.", yd, bold=True)
    yd -= 2
    yd = para("SIDE STAKES: house edge Perfect Pairs 6.1%, 4-Card Total 4.5%. Only play them when the bet plan "
              "says so (catch-up spots).", yd)
    yd -= 2
    if rep:
        mm = rep["main"]["optimizer"]
        yd = para("SIM RESULTS (win % of decided matches; break-even 55.56%): "
                  + ", ".join(f"{rep['model_names'][k].split(' (')[0]} {100 * mm[k]['dec_rate']:.1f}%"
                              for k in ["sharp_a", "casual_a", "casual_b", "sharp_c"])
                  + (f", near-mirror {100 * rep['near_mirror']['dec_rate']:.1f}%" if "near_mirror" in rep else "")
                  + ". Sharp B (exact mirror) always ties.", yd)
    c.setFont("Helvetica-Oblique", 6)
    c.drawString(m, 12, "6-minute clock: don't overthink. Timing out forfeits the match. Odds are estimates from simulation, not guarantees.")
    c.showPage()
    c.save()
    return path


if __name__ == "__main__":
    print(build())
