# 21 Rivals advisor + simulator

A local web app (runs on your Mac, opens on an iPhone on the same Wi-Fi) plus a Python simulation engine for DraftKings **21 Rivals**, the head-to-head 5-hand blackjack game.

It does three things:

1. **Advises** every decision during a match: bet size, side stakes, insurance, hit/stand/double/split.
2. **Proves** (or disproves) the strategy by simulating millions of full matches with the exact shared-shoe rule. See [`results/REPORT.md`](results/REPORT.md).
3. **Logs** real matches in SQLite and compares real results against the simulation.

The results summary is at the bottom of this file. **Read the "What this depends on" section before putting money behind it.**

---

## 1. Mac setup (one time, about 10 minutes)

You need Python 3.10 or newer. The `python3` that ships with macOS is usually too old.

1. Install Python 3.12 from <https://www.python.org/downloads/macos/>: download, double-click, click through.
2. Get this code. On GitHub, open the repo, switch to the branch, click **Code → Download ZIP**, then unzip it somewhere like `~/21-Rivals`. Or, if you use git:

```bash
git clone https://github.com/smallshaft/21-Rivals.git ~/21-Rivals
```

3. Open **Terminal** (Cmd+Space, type "Terminal") and run these one at a time:

```bash
cd ~/21-Rivals
```

```bash
python3.12 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

4. Optional, but checks everything works (about 1 minute; all tests should pass):

```bash
python -m pytest -q
```

## 2. Running the app

Every time you want to use it:

```bash
cd ~/21-Rivals && source .venv/bin/activate && caffeinate -i python -m web.app
```

(`caffeinate -i` keeps the Mac from sleeping while the app runs. Stop it with Ctrl+C.)

The **first** launch builds the strategy (1–2 minutes; later launches take a few seconds). The terminal prints something like:

```
  On this Mac:            http://localhost:8021
  On iPhone (same Wi-Fi): http://192.168.1.23:8021
```

### Opening it on your dad's iPhone

1. The iPhone must be on the **same Wi-Fi** as the Mac.
2. If macOS asks "Do you want the application Python to accept incoming network connections?", click **Allow**. If you missed it: System Settings → Network → Firewall → Options → set Python to "Allow incoming connections".
3. On the iPhone, open **Safari** and type the `http://192.168.x.x:8021` address exactly as printed (including `http://` and `:8021`).
4. If the printed address doesn't work, find the Mac's IP yourself with the command below, then use `http://<that number>:8021`:

```bash
ipconfig getifaddr en0
```

5. Make it feel like an app: tap **Share → Add to Home Screen**.

The Mac's IP can change when the router restarts. If the bookmark stops working, re-check the address.

## 3. Using it during a match (6-minute clock)

**Advisor tab**
1. Pick the hand number (1–5), type current chips, tap **Get bet**. It shows the main bet plus any side stakes (Perfect Pairs / 4-Card Total). It's usually "none".
2. Tap your two cards, then the dealer's upcard. `10` covers 10/J/Q/K.
3. If you're dealt a pair with a Perfect Pairs stake out, it asks which kind of pair (mixed / same color / perfect).
4. Dealer ace: it says TAKE or NO INSURANCE. Tap what you actually did.
5. It shows the action in big letters. After a HIT or DOUBLE, tap the card you got; it re-prompts. SPLIT walks you through hand 1, then hand 2.
6. When the hand is over, type chips after the hand and tap **Next hand**. After hand 5 it jumps to the Log tab.

Responses are instant (under 10 ms on the server). The orange "Not basic strategy" tag marks spots where the match situation changes the play. "Toss-up" means the options are within 0.2% of each other, so either is fine.

**Log tab:** after every match, record W/L/T, entry, your final chips and the opponent's final chips (shown at the end of each match). **Log every match, including losses and matches where you didn't follow the advice.** Otherwise the dashboard lies to you.

**Results tab:** real win rate with a 99% confidence range vs the simulation's prediction, P&L chart, ROI by entry size, and an estimate of what kind of opponents you're actually facing (from their final scores).

**Settings tab:** opponent mix weights, rule flags, default entry size. Saving re-optimizes the strategy in the background (~1 minute).

**Cheat sheet:** `results/cheatsheet.pdf` (also linked on the Results tab). One page: the bet plan, basic strategy chart, main deviations, insurance rule. Regenerate it after changing settings:

```bash
python -m rivals.cheatsheet
```

## 4. Re-running the proof

```bash
python -m rivals.validate
```

Full run: 10M matches per main matchup, fixed seeds, about 30–60 minutes on a recent Mac. It writes `results/REPORT.md` and `results/report.json`. Then:

```bash
python -m rivals.robustness
```

That plays the strategy against opponents it wasn't tuned for. Add `--quick` to `validate` for a ~5 minute smoke test.

---

## 5. How it works (short version)

- **Engine** (`rivals/core.py`, compiled with numba): exact rules. One fixed 6-deck shoe order per match. Each player reads the same card sequence from their own position, so identical decisions mean identical cards; after a divergence, each player's cards differ. Unit tests (`tests/test_engine.py`) prove this on hand-built shoes.
- **Basic strategy** isn't typed in; it's derived by the engine's own expectimax with chip-EV as the objective, then checked against the published chart.
- **Optimizer** (`rivals/optimizer.py`):
  - The objective is **expected profit per match**: +0.8 entry for a win, −1 for a loss, 0 for a tie. This is "maximize P(win)" with ties correctly counted as refunds, not expected chips. You can switch to pure P(win) in Settings.
  - It simulates each opponent type to get the distribution of their final chips, mixes them by the population weights, then runs a backward DP over (hand #, my chips) to pick bet + side stakes.
  - Every in-hand decision is an expectimax against that value function, so play can deviate from basic strategy when the match situation calls for it.
- **Validation** (`rivals/validate.py`): brute-force head-to-head matches with the real shared shoe. This, not the optimizer's internal estimate, is the source of every number in the report.

## 6. What this depends on (read this)

- **Opponent models are guesses.** The edge comes almost entirely from opponents who *don't* shape their bets to win the match. Against someone doing roughly what this app does (the "near-mirror" test), you lose money after rake. The real pool is unknown until you log matches.
- **The optimizer assumes your opponent's cards are independent of yours.** They aren't: same shoe. Validation models this exactly, so the reported win rates are honest. But the in-app "Est. win %" is the optimizer's internal number, not the validated one.
- **Unconfirmed rules** (flags in Settings, tested in the report): dealer peek, whether the dealer draws when you've busted (changes card order after divergence), splitting K-Q, whether A-8/A-9 count as "9/10" for doubling. Also assumed: side-stake wins are paid at the end of the hand (not usable for a double), and you can't double/split/insure without enough chips behind the bet.
- **Not modeled:** the 6-minute clock (assumed nobody times out), card counting within the shoe, opponents who change behavior based on their own running score.
- **Terms of Use risk.** I couldn't find a 21 Rivals-specific rule on outside help. DraftKings' launch page for the game ([dknetwork.draftkings.com](https://dknetwork.draftkings.com/2026/11/10/21-rivals-draftkings-head-to-head-card-game-launch/)) doesn't mention one, and the main terms pages blocked automated fetching. But:
  - The DraftKings Terms of Use prohibit "using automated means (including but not limited to scripts and third-party tools) to interact with the Website" ([summary of the clause](https://conductatlas.com/platform/draftkings/draftkings-terms-of-use/provision/CA-P-039377/automated-means-to-interact-with-website-prohibited/)). This app never touches DraftKings: your dad reads and taps everything himself. "Third-party tools" is still broad enough that DraftKings could argue it applies.
  - DraftKings' international terms explicitly ban "software-assisted methods" during play. The US terms bar collusion and account sharing, so he should play only on his own account.
  - Read the in-app Skill Games rules / Terms before playing. If they ban outside assistance, account closure and forfeited winnings are the realistic risk.

## 7. Files

```
rivals/config.py      rules, opponent profiles, mix, settings storage
rivals/core.py        numba engine: shoe, hands, expectimax, match sim, DP step
rivals/strategy.py    dealer tables, basic strategy, split tables, exact side-stake math
rivals/optimizer.py   opponent distributions, DP, plan caching
rivals/validate.py    big simulation runs + statistics -> results/
rivals/robustness.py  plan vs opponents it wasn't tuned for
rivals/report.py      results/REPORT.md writer
rivals/advisor.py     live advice API used by the web app
rivals/db.py          SQLite match log + dashboard stats + pool-mix estimate
rivals/cheatsheet.py  printable PDF
web/app.py            Flask server;  web/templates/index.html  the phone UI
tests/                pytest suite
data/                 your settings + matches.sqlite3 (not committed)
```

---

## 8. Results summary (from `results/REPORT.md`, 10M matches per matchup)

Win % of **decided** matches (ties refund). Break-even after the 10% rake is **55.56%** at every entry size.

| Opponent | This app | Basic strategy + 10 bets | Basic + flat 200 |
|---|---|---|---|
| Sharp A (basic strategy, flat 25–200) | **66.4%** | 51.4% | 48.6% |
| Sharp B (exact mirror of this app) | 100% ties | - | - |
| Casual A (gut feel) | **62.1%** | 54.3% | 51.5% |
| Casual B (degen) | **68.0%** | 67.4% | 66.4% |
| Near-mirror (this plan, bets ±30%) | **48.7%: loses** | - | - |
| Default mix (25% sharp / 75% casual) | **65.2%**, 99% CI [65.21, 65.26] | 55.5% | 56.2% |

- **Where the edge comes from:** bet sizing. The app bets big early (310 on hand 1), locks in any lead with minimum bets, and goes big with side stakes only when behind late. It exploits opponents whose final scores bunch near 1,000. Playing basic strategy with the app's bets gives essentially the same result: the in-hand deviations are worth about 0 points. Side stakes in catch-up spots add about +0.5 to +0.9 points vs Sharp A and Casual A.
- **Break-even sharp %:**
  - With "sharp" defined as requested (half flat-betting basic players, half exact mirrors): there is none. Flat bettors are easy and mirrors only tie.
  - With "sharp" defined as match-aware players who also shape their bets (near-mirror): profitable only if **under ~43%** of opponents are like that.
  - Both hold at every entry size.
- **Fragility:** against opponent types it wasn't tuned for, results range from 54.5% (a degen who shoves exactly once) to 73% (min-betting sharps). Casuals betting 100–500 come out at 56.5%, barely above break-even.
- **Rule flags barely matter:** no-peek, dealer draws after you bust, and splitting K-Q all land within ±0.1 points.
