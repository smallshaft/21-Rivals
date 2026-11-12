"""SQLite match log + dashboard statistics."""
from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import date

import numpy as np

from .config import DATA_DIR, RESULTS_DIR, ENTRIES, BREAKEVEN, MODEL_KEYS, MODEL_NAMES

DB_PATH = os.path.join(DATA_DIR, "matches.sqlite3")


def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        played_on TEXT NOT NULL,
        entry INTEGER NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('W','L','T')),
        my_chips REAL,
        opp_chips REAL,
        followed_advice INTEGER DEFAULT 1,
        notes TEXT DEFAULT ''
    )""")
    return c


def add_match(entry, result, my_chips=None, opp_chips=None, played_on=None, followed=1, notes=""):
    result = result.upper()
    if result not in ("W", "L", "T"):
        raise ValueError("result must be W, L or T")
    if int(entry) not in ENTRIES:
        raise ValueError("entry must be one of %s" % list(ENTRIES))
    with conn() as c:
        cur = c.execute("INSERT INTO matches (played_on, entry, result, my_chips, opp_chips, followed_advice, notes)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (played_on or date.today().isoformat(), int(entry), result,
                         None if my_chips in (None, "") else float(my_chips),
                         None if opp_chips in (None, "") else float(opp_chips), int(followed), notes or ""))
        return cur.lastrowid


def delete_match(mid):
    with conn() as c:
        c.execute("DELETE FROM matches WHERE id=?", (int(mid),))


def list_matches():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM matches ORDER BY played_on, id")]


def profit(entry, result):
    if result == "W":
        return ENTRIES[entry] - entry
    if result == "L":
        return -float(entry)
    return 0.0


def wilson(k, n, z):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def sim_prediction():
    path = os.path.join(RESULTS_DIR, "report.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        rep = json.load(f)
    m = rep["main"]["optimizer"]["_default_mix"]
    def clean(x):
        return None if (x is None or (isinstance(x, float) and math.isnan(x))) else x
    out = {"dec_rate": m["dec_rate"], "dec_ci99": m["dec_ci99"], "tie": m["tie"],
           "ev_per_dollar": m["ev_per_dollar"], "per_model": {}}
    for k in MODEL_KEYS:
        r = rep["main"]["optimizer"].get(k)
        if r:
            out["per_model"][k] = {"dec_rate": clean(r["dec_rate"]), "tie": r["tie"]}
    if "near_mirror" in rep:
        out["near_mirror"] = rep["near_mirror"]["dec_rate"]
    return out


def estimate_pool_mix(opp_scores, iters=500):
    """EM estimate of the opponent population mix from logged opponent final chips,
    using each model's simulated final-chip distribution (smoothed)."""
    path = os.path.join(RESULTS_DIR, "sim_hist.npz")
    if not os.path.exists(path) or len(opp_scores) == 0:
        return None
    z = np.load(path)
    keys = [k for k in MODEL_KEYS if f"opp_{k}" in z.files]
    kernel = np.ones(21) / 21.0        # +/- 25 chips smoothing
    dens = []
    for k in keys:
        h = z[f"opp_{k}"].astype(float)
        h = np.convolve(h / h.sum(), kernel, mode="same") + 1e-9
        dens.append(h / h.sum())
    dens = np.array(dens)
    idx = np.clip((np.asarray(opp_scores, float) / 2.5).round().astype(int), 0, dens.shape[1] - 1)
    lik = dens[:, idx]                       # [models, n]
    w = np.ones(len(keys)) / len(keys)
    for _ in range(iters):
        r = w[:, None] * lik
        r /= r.sum(axis=0, keepdims=True)
        w = r.mean(axis=1)
    sharp = sum(w[i] for i, k in enumerate(keys) if k.startswith("sharp"))
    return {"weights": {k: float(w[i]) for i, k in enumerate(keys)},
            "names": {k: MODEL_NAMES[k] for k in keys}, "sharp_share": float(sharp),
            "n": int(len(opp_scores)),
            "note": "Rough. Sharp A/B/C and casuals overlap a lot near 1,000 chips; "
                    "needs 100+ logged opponent scores before it means much."}


def dashboard():
    ms = list_matches()
    n = len(ms)
    w = sum(1 for m in ms if m["result"] == "W")
    l = sum(1 for m in ms if m["result"] == "L")
    t = n - w - l
    pnl = []
    run = 0.0
    for m in ms:
        run += profit(m["entry"], m["result"])
        pnl.append({"id": m["id"], "date": m["played_on"], "pnl": round(run, 2)})
    by_entry = {}
    for e in ENTRIES:
        sub = [m for m in ms if m["entry"] == e]
        if not sub:
            continue
        p = sum(profit(e, m["result"]) for m in sub)
        we = sum(1 for m in sub if m["result"] == "W")
        le = sum(1 for m in sub if m["result"] == "L")
        by_entry[str(e)] = {"n": len(sub), "wins": we, "losses": le, "profit": p,
                            "roi": p / (e * len(sub)),
                            "dec_rate": we / (we + le) if we + le else None}
    dec = w + l
    real = {"n": n, "wins": w, "losses": l, "ties": t,
            "dec_rate": w / dec if dec else None,
            "ci95": wilson(w, dec, 1.959964), "ci99": wilson(w, dec, 2.575829),
            "profit": run, "wagered": float(sum(m["entry"] for m in ms))}
    sim = sim_prediction()
    verdict = None
    if dec >= 1 and sim:
        lo, hi = real["ci99"]
        if lo > BREAKEVEN:
            verdict = "Real results are profitable with 99% confidence."
        elif hi < BREAKEVEN:
            verdict = "Real results are LOSING with 99% confidence. Stop or drop to $1 and re-check the opponent mix."
        else:
            verdict = (f"Not enough matches yet to tell. 99% CI is {100 * lo:.1f}% to {100 * hi:.1f}%, "
                       f"which straddles the 55.56% break-even.")
        if not (lo <= sim["dec_rate"] <= hi):
            verdict += (f" The sim predicts {100 * sim['dec_rate']:.1f}%, which is OUTSIDE your real 99% CI, "
                        "so the model does not match reality.")
    opp = [m["opp_chips"] for m in ms if m["opp_chips"] is not None]
    return {"real": real, "sim": sim, "pnl": pnl, "by_entry": by_entry, "verdict": verdict,
            "pool": estimate_pool_mix(opp), "breakeven": BREAKEVEN, "matches": ms}
