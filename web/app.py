"""
Local web app.   Run from the project folder:   python -m web.app
Then open the printed URL on any phone on the same Wi-Fi.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import traceback

from flask import Flask, jsonify, request, send_from_directory, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rivals import db  # noqa: E402
from rivals.config import (Settings, load_settings, save_settings, MODEL_KEYS, MODEL_NAMES,  # noqa: E402
                           ENTRIES, RESULTS_DIR)
from rivals.advisor import Advisor  # noqa: E402

app = Flask(__name__, template_folder="templates", static_folder="static")
STATE = {"advisor": None, "status": "starting", "error": None}


def _load(settings=None):
    try:
        STATE["status"] = "computing strategy (first run or new settings: ~2-5 min)."
        if STATE["advisor"] is None:
            STATE["advisor"] = Advisor(settings)
        else:
            STATE["advisor"].load(settings or load_settings())
        STATE["status"] = "ready"
        STATE["error"] = None
    except Exception as e:  # pragma: no cover
        traceback.print_exc()
        STATE["status"] = "error"
        STATE["error"] = str(e)


def adv() -> Advisor:
    if STATE["advisor"] is None:
        raise RuntimeError("Strategy still loading: " + STATE["status"])
    return STATE["advisor"]


@app.errorhandler(Exception)
def on_error(e):
    traceback.print_exc()
    return jsonify({"error": str(e)}), 400


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cheatsheet.pdf")
def cheatsheet():
    return send_from_directory(RESULTS_DIR, "cheatsheet.pdf")


@app.route("/report")
def report():
    path = os.path.join(RESULTS_DIR, "REPORT.md")
    txt = open(path).read() if os.path.exists(path) else "No report yet. Run: python -m rivals.validate"
    return app.response_class(txt, mimetype="text/plain")


@app.route("/api/status")
def status():
    return jsonify({"status": STATE["status"], "error": STATE["error"]})


@app.route("/api/prehand", methods=["POST"])
def prehand():
    d = request.get_json(force=True)
    return jsonify(adv().prehand(int(d["hand"]), float(d["chips"]), d.get("history") or []))


@app.route("/api/insurance", methods=["POST"])
def insurance():
    return jsonify(adv().insurance(request.get_json(force=True)))


@app.route("/api/action", methods=["POST"])
def action():
    return jsonify(adv().action(request.get_json(force=True)))


@app.route("/api/matches", methods=["GET", "POST"])
def matches():
    if request.method == "POST":
        d = request.get_json(force=True)
        mid = db.add_match(d["entry"], d["result"], d.get("my_chips"), d.get("opp_chips"),
                           d.get("played_on"), int(d.get("followed", 1)), d.get("notes", ""))
        return jsonify({"id": mid})
    return jsonify(db.list_matches())


@app.route("/api/matches/<int:mid>", methods=["DELETE"])
def del_match(mid):
    db.delete_match(mid)
    return jsonify({"ok": True})


@app.route("/api/dashboard")
def dashboard():
    return jsonify(db.dashboard())


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        s = Settings.from_dict(request.get_json(force=True))
        save_settings(s)
        threading.Thread(target=_load, args=(s,), daemon=True).start()
        return jsonify({"ok": True})
    s = load_settings()
    import json
    d = json.loads(s.to_json())
    d["model_names"] = MODEL_NAMES
    d["model_keys"] = MODEL_KEYS
    d["entries"] = list(ENTRIES)
    return jsonify(d)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8021))
    threading.Thread(target=_load, daemon=True).start()
    ip = lan_ip()
    print("\n" + "=" * 60)
    print(f"  21 Rivals advisor running.")
    print(f"  On this Mac:          http://localhost:{port}")
    print(f"  On iPhone (same Wi-Fi): http://{ip}:{port}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
