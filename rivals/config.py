"""
Configuration: game rules, opponent profiles, population mix, economics.

Everything that is an *assumption* (not confirmed from the app) is a flag
here so it can be changed in the web app's Settings screen and re-tested.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _writable(path: str, fallback_name: str) -> str:
    """Use `path` if we can write there; otherwise a per-user folder macOS always allows
    (Desktop/Downloads/iCloud folders can raise 'Operation not permitted')."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except OSError:
        alt = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "21Rivals", fallback_name)
        os.makedirs(alt, exist_ok=True)
        return alt


DATA_DIR = _writable(os.path.join(ROOT, "data"), "data")
RESULTS_DIR = os.path.join(ROOT, "results")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
CACHE_DIR = _writable(os.path.join(RESULTS_DIR, "cache"), "cache")

START_CHIPS = 1000.0
N_HANDS = 5
CHIP_STEP = 2.5          # all chip amounts are multiples of 2.5 (3:2 on a 5-multiple, half-stake insurance)
NUM_DECKS = 6

# Entry fee -> total payout if you win (10% rake on the $2E pot).
ENTRIES = {1: 1.80, 5: 9.0, 10: 18.0, 20: 36.0}
WIN_PROFIT_RATIO = 0.80  # net profit per $1 of entry when you win
BREAKEVEN = 1.0 / 1.8    # 55.56% of decided (non-tie) matches


@dataclass
class Rules:
    # Confirmed rules (still flags so tests can poke them)
    dealer_peeks: bool = True            # dealer checks for BJ under A / ten before you act
    double_after_split: bool = True
    # Assumptions (NOT confirmed from the app)
    split_by_value: bool = False         # False: only same rank (K-K). True: any two 10-values (K-Q)
    double_soft_low: bool = False        # True: A-8 / A-9 count as "showing 9/10" for doubling
    dealer_draws_if_all_bust: bool = False  # does the dealer still draw cards if you busted?
    side_min: float = 5.0
    side_max_frac: float = 1.0           # side stake max as fraction of balance
    min_bet: float = 10.0

    def as_int_array(self) -> np.ndarray:
        """Packed form passed into the numba engine."""
        return np.array([
            int(self.dealer_peeks), int(self.double_after_split), int(self.split_by_value),
            int(self.double_soft_low), int(self.dealer_draws_if_all_bust),
        ], dtype=np.int64)


# --------------------------------------------------------------------------
# Opponent profiles.  Every non-optimizer player in the engine is a
# "parametric" player: basic strategy + bet/side/insurance habits + mistakes.
# Layout of the float parameter vector (see engine.py, P_* constants).
# --------------------------------------------------------------------------
@dataclass
class Profile:
    name: str
    bets: list = field(default_factory=lambda: [100.0])  # bet choices
    bet_per_match: bool = True     # pick one bet for the whole match (True) or per hand (False)
    p_insurance: float = 0.0       # chance to take insurance when offered
    p_stand_stiff: float = 0.0     # chance to stand 12-16 vs 7-A when basic says hit
    p_skip_double: float = 0.0     # chance to skip a correct double
    p_skip_split: float = 0.0      # chance to skip a correct split
    p_side: float = 0.0            # chance (per hand, per side stake) to play a side stake
    side_min: float = 5.0
    side_max: float = 25.0
    allin_hands: float = 0.0       # how many hands to shove (1.5 = 1 or 2 at random)
    allin_frac: float = 1.0        # fraction of balance on a shove
    p_error: float = 0.0           # random hit/stand flip on 12-18 totals

    def as_params(self) -> np.ndarray:
        p = np.zeros(20)
        b = list(self.bets)[:6]
        for i, v in enumerate(b):
            p[i] = v
        p[6] = 1.0 if self.bet_per_match else 0.0
        p[7] = self.p_insurance
        p[8] = self.p_stand_stiff
        p[9] = self.p_skip_double
        p[10] = self.p_skip_split
        p[11] = self.p_side
        p[12] = self.side_min
        p[13] = self.side_max
        p[14] = self.allin_hands
        p[15] = self.allin_frac
        p[16] = self.p_error
        return p


DEFAULT_PROFILES = {
    "sharp_a": Profile("Sharp A (basic strategy, flat bets)",
                       bets=[25, 50, 100, 200], bet_per_match=True),
    # sharp_b is the mirror match: it plays OUR optimizer. No parameters.
    "casual_a": Profile("Casual A (gut feel)",
                        bets=[25, 50, 100, 150, 200], bet_per_match=False,
                        p_insurance=0.6, p_stand_stiff=0.45, p_skip_double=0.35,
                        p_skip_split=0.35, p_side=0.35, side_min=5, side_max=25,
                        p_error=0.08),
    "casual_b": Profile("Casual B (degen)",
                        bets=[50, 100, 200, 250], bet_per_match=False,
                        p_insurance=0.35, p_stand_stiff=0.25, p_skip_double=0.2,
                        p_skip_split=0.2, p_side=0.7, side_min=10, side_max=100,
                        allin_hands=1.5, allin_frac=1.0, p_error=0.08),
}

MODEL_KEYS = ["sharp_a", "sharp_b", "casual_a", "casual_b", "sharp_c"]
MODEL_NAMES = {
    "sharp_a": "Sharp A (basic, flat bets)",
    "sharp_b": "Sharp B (mirror: same optimizer)",
    # Extra stress-test model (not requested, weight 0 by default): a match-aware
    # player who ALSO shapes bets to win the match, but optimized against a
    # different belief (that everyone is a flat-betting Sharp A). This is the
    # realistic "smart regular who doesn't use this exact tool".
    "sharp_c": "Sharp C (match-aware, own model)",
    "casual_a": "Casual A (gut feel)",
    "casual_b": "Casual B (degen)",
}

DEFAULT_MIX = {"sharp_a": 0.125, "sharp_b": 0.125, "casual_a": 0.375, "casual_b": 0.375,
               "sharp_c": 0.0}


@dataclass
class Settings:
    rules: Rules = field(default_factory=Rules)
    mix: dict = field(default_factory=lambda: dict(DEFAULT_MIX))
    profiles: dict = field(default_factory=lambda: {k: asdict(v) for k, v in DEFAULT_PROFILES.items()})
    entry: int = 1
    objective: str = "money"   # "money": maximize 0.8*P(win) - P(loss).  "winprob": maximize P(win)

    def profile(self, key: str) -> Profile:
        return Profile(**self.profiles[key])

    def to_json(self) -> str:
        return json.dumps({"rules": asdict(self.rules), "mix": self.mix,
                           "profiles": self.profiles, "entry": self.entry,
                           "objective": self.objective}, indent=2)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        s = Settings()
        if "rules" in d:
            s.rules = Rules(**{**asdict(Rules()), **d["rules"]})
        if "mix" in d:
            s.mix = {k: float(d["mix"].get(k, 0.0)) for k in MODEL_KEYS}
        if "profiles" in d:
            for k, v in d["profiles"].items():
                if k in s.profiles:
                    s.profiles[k] = {**s.profiles[k], **v}
        s.entry = int(d.get("entry", s.entry))
        s.objective = d.get("objective", s.objective)
        return s

    def key(self) -> str:
        """Hash of everything that changes the optimal strategy (not entry size)."""
        import hashlib
        blob = json.dumps({"rules": asdict(self.rules), "mix": self.mix,
                           "profiles": self.profiles, "objective": self.objective},
                          sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:12]


def load_settings() -> Settings:
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH) as f:
            return Settings.from_dict(json.load(f))
    return Settings()


def save_settings(s: Settings) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        f.write(s.to_json())
