"""
SkantBot v0.3 - Fullhouse Hackathon entry
==========================================

Refactor of v0.2.1 into a fully parametric architecture suitable for
Optuna sweeps via Guneet's harness.

Key architectural changes from v0.2.1:
  - Single Config dataclass; every threshold/frequency/trigger on it.
  - Environment-variable loading (SKANT_<FIELD>) for harness injection.
  - Mixed-strategy preflop ranges (dict[hand, freq]) instead of sets.
  - Stack-aware tightness as a first-class multiplier.
  - Multiway c-bet penalty.
  - Field-shrink range widening (single parameter, interpolated).
  - Cold-start caution (shifts equity thresholds when opponent unknown).
  - Deterministic per-hand RNG (initialized from hand_id) for CRN compat.
  - All literals from v0.2.1 stack-preservation guards now Config fields.

Code structure (strict order, per spec):
  1. Imports
  2. Engine constants (immutable, given by rules)
  3. @dataclass Config and load_config_from_env()
  4. Range data (preflop charts as freq dicts)
  5. Helper functions (pure utilities, no decision logic)
  6. Opponent modelling (stat tracking + queries)
  7. Position derivation
  8. Equity calculation
  9. Preflop decision
  10. Postflop decision
  11. decide() entry point
"""

# ============================================================================
# 1. IMPORTS
# ============================================================================

# NOTE: This is the SUBMISSION version of skantbot. It does NOT import os
# because the tournament validator forbids it. Config values are baked in
# as defaults below — these reflect the best parameters from the Optuna sweep.
#
# For tuning, use harness/skantbot_dev/bot.py which keeps load_config_from_env().
# After each sweep, copy the best parameters into the Config defaults below
# and re-validate this file with python sandbox/validator.py bots/skantbot4/bot.py

import random
import math
import time
import statistics
from dataclasses import dataclass, fields
INITIAL_STACK = 10000
our_match_delta = 0
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

try:
    import eval7
    HAVE_EVAL7 = True
except ImportError:
    HAVE_EVAL7 = False


BOT_NAME = "SkantBot"
BOT_AVATAR = "robot_1"


# ============================================================================
# 2. ENGINE CONSTANTS (rules-given, never tuned)
# ============================================================================

BIG_BLIND = 100
SMALL_BLIND = 50
STARTING_STACK = 10000
RANKS = "23456789TJQKA"
RANK_IDX = {r: i for i, r in enumerate(RANKS)}


# ============================================================================
# 3. CONFIG DATACLASS + ENV LOADER
# ============================================================================

@dataclass
class Config:
    # --- Preflop tightness offsets ---
    # Multiplied into raise frequencies. 1.0 = chart values, >1 = looser.
    rfi_tightness: float = 2.023082215163377
    threebet_tightness: float = 0.9389205262640616
    fourbet_tightness: float = 1.092042750527517

    # --- Position-specific aggression multipliers ---
    pos_aggression_lj: float = 1.0
    pos_aggression_hj: float = 1.0
    pos_aggression_co: float = 1.0
    pos_aggression_btn: float = 1.0
    pos_aggression_sb: float = 1.0
    pos_aggression_bb: float = 1.0

    # --- Stack-aware tightness curve ---
    # Default OFF (1.0) - exposed for Optuna to tune.
    # Empirically, aggressive tightening at shallow depths hurt more than helped
    # against the reference field. Optuna can find the right curve per opponent pool.
    stack_full_threshold_bb: float = 80.0
    stack_short_threshold_bb: float = 30.0
    stack_short_tightness: float = 1.0762061840378374

    # --- Field-shrink widening (4-handed and below) ---
    # When n_active < 6, we widen ranges proportionally toward HU.
    # widening_factor = 1.0 + shrink_widening_factor * (6 - n_active)
    shrink_widening_factor: float = 0.026810028607063694

    # --- Cold-start caution ---
    # Adds to call thresholds when we don't have enough hands on opponent.
    # Default 0 (off) - exposed for Optuna to tune. Setting >0 makes us
    # tighter when calling against unknowns, but can leak EV by missing calls.
    cold_start_caution: float = 0.002449632443842318
    cold_start_threshold_hands: int = 6

    # --- Postflop equity thresholds ---
    equity_value_bet: float = 0.6742204695843986        # bet for value above this
    equity_thin_value: float = 0.556869736559658       # thin value-bet IP only
    equity_call_threshold: float = 0.3691653581459096   # marginal call threshold
    equity_raise_threshold: float = 0.8410228422223449  # raise instead of just call
    pot_odds_buffer_normal: float = 0.0550471419694941  # extra equity required vs pot odds
    pot_odds_buffer_marginal: float = 0.2785636487959463 # how much pot we'll call vs marginal eq

    # --- Stack preservation guard ---
    # When facing a bet, the % of stack at risk triggers different thresholds.
    stack_risk_high_threshold: float = 0.30        # 30%+ risk = high
    stack_risk_medium_threshold: float = 0.15      # 15-30% risk = medium
    stack_risk_high_eq_normal: float = 0.8871115108334615        # equity needed if high risk, normal opp
    stack_risk_high_eq_maniac: float = 0.835030979114687        # equity needed if high risk, vs maniac
    stack_risk_med_eq_normal: float = 0.6480868366218109
    stack_risk_med_eq_maniac: float = 0.6059026626821016

    # --- Jam-or-fold logic ---
    fourbet_commit_threshold: float = 0.25         # if 4-bet would commit >25% of stack, jam-or-fold
    shallow_jam_threshold_bb: float = 40.0         # if stack <40bb facing 3-bet, jam-or-fold
    fourbet_call_threshold_pct: float = 0.15       # cap on calling 3-bets out-of-position
    threebet_call_threshold_pct: float = 0.15      # cap on calling raises with weaker hands

    # --- C-bet (continuation bet) ---
    cbet_freq_base: float = 0.7121471595595862
    k_texture_paired: float = 0.12351186867990399
    k_texture_monotone: float = 0.15185502288214223
    k_texture_connected: float = -0.06232178343913977
    k_texture_high_card: float = -0.012219977581729732
    spr_commit_threshold: float = 5.467424844726562
    spr_smoothness: float = 1.122830208366453
    k_commit: float = 0.015429638425628965
    river_mdf_aggression: float = 1.3928031863008083
    river_v2b_half_pot: float = 2.0
    river_v2b_pot_sized: float = 1.0
    river_v2b_overbet: float = 0.5
    k_river_bluff_blocker: float = -0.014521617050010389
    k_standing: float = 0.34526882993639224
    standing_alpha: float = 0.024589299495701714
    standing_beta: float = 0.25498359496156964
    river_value_thin_threshold: float = 0.6515627305014043
    river_value_strong_threshold: float = 0.8156577287898198

    # --- Thin Value OOP / Passive Opponents ---
    oop_passive_value_threshold: float = 0.50
    oop_passive_value_size: float = 0.40
    passive_aggression_threshold: float = 0.30

    river_value_thin_size: float = 0.50
    river_value_strong_size: float = 0.85
    cbet_size_pct: float = 0.5729317820122599

    # --- Small open defense ---
    small_open_threshold_bb: float = 2.1613359877861003
    small_open_3bet_boost: float = 1.2654311725115979
    small_open_call_boost: float = 1.487176114615579

    # Multiway penalty: cbet_freq *= cbet_multiway_penalty ^ (n_opp - 1).
    # Default 0.75 = mild penalty (cbet 56% of normal vs 2 opps, 42% vs 3 opps).
    # Optuna can tune lower if pool tends to be sticky multiway.
    cbet_multiway_penalty: float = 0.7947658787534136

    # --- Bluff frequencies ---
    bluff_freq_ip: float = 0.16478734627553582
    bluff_freq_oop: float = 0.11186466290978737
    fourbet_bluff_freq: float = 0.30

    # --- Bet sizing presets (fractions of pot) ---
    sizing_value: float = 0.823254302571333
    sizing_polarised: float = 1.00
    sizing_thin: float = 0.40

    # --- Preflop sizing multipliers ---
    open_size_bb: float = 2.2792270345075467
    threebet_size_ip: float = 2.97646771991361
    threebet_size_oop: float = 4.434500746284703
    fourbet_size_ip: float = 2.3
    fourbet_size_oop: float = 2.5

    variance_c: float = 0.08068442293680263
    # --- Opponent modelling ---
    k_bluff_vs_cbet_folder: float = 0.33817778329790854
    k_bluff_vs_2barrel_folder: float = 0.08904047918186145
    k_bluff_vs_3barrel_folder: float = 0.4408983942594556
    k_bluff_vs_wtsd: float = 0.15458700220752056
    k_value_size_vs_station: float = 0.42451659667981206
    k_tightness_vs_3bet_freq: float = 0.2675278617433117
    k_call_threshold_vs_aggression: float = 0.08609833783127877
    k_4bet_vs_3bet_freq: float = 0.008307951286571025
    prior_weight: float = 15.0                     # Bayesian prior strength
    min_hands_for_exploit: int = 25
    fold_to_3bet_exploit_threshold: float = 0.70
    maniac_min_sample: int = 6
    maniac_vpip_threshold: float = 0.5273385541287454
    maniac_pfr_threshold: float = 0.40
    station_min_sample: int = 8
    station_vpip_threshold: float = 0.35404883602998494
    station_pfr_threshold: float = 0.15

    # --- Time/sim budget ---
    mc_sims_flop: int = 300
    mc_sims_turn: int = 400
    mc_sims_river: int = 600
    time_budget_sec: float = 1.6


CONFIG = Config()


# ============================================================================
# 4. RANGE DATA (preflop charts as freq dicts)
# ============================================================================

# Source: PokerCoaching "Implementable GTO" charts, 100bb cash, no rake.
# Format: dict[hand_class] -> raise_frequency in [0.0, 1.0]
# Defaults are 1.0 for hands in chart, 0.0 implied for hands not present.
# This structure supports mixed strategies (e.g. K7s with 0.6 raise freq).

def _expand_to_freq_dict(range_str: str, freq: float = 1.0) -> Dict[str, float]:
    """Parse a range string and return {hand: freq} for every hand in it."""
    result = {}
    if not range_str or not range_str.strip():
        return result

    for raw in range_str.split(","):
        part = raw.strip()
        if not part:
            continue
        try:
            # Pocket pairs
            if len(part) >= 2 and part[0] == part[1]:
                r = part[0]
                if len(part) == 2:
                    result[r + r] = freq
                elif part[2:] == "+":
                    idx = RANK_IDX[r]
                    for i in range(idx, len(RANKS)):
                        result[RANKS[i] + RANKS[i]] = freq
                elif "-" in part:
                    bits = part.split("-")
                    hi = bits[0][0]
                    lo = bits[1][0]
                    for i in range(RANK_IDX[lo], RANK_IDX[hi] + 1):
                        result[RANKS[i] + RANKS[i]] = freq
                continue
            # Non-pairs
            if len(part) >= 3:
                r1, r2, suit = part[0], part[1], part[2]
                if suit not in ("s", "o"):
                    continue
                if len(part) == 3:
                    result[r1 + r2 + suit] = freq
                elif part[3:] == "+":
                    idx2 = RANK_IDX[r2]
                    idx1 = RANK_IDX[r1]
                    for i in range(idx2, idx1):
                        result[r1 + RANKS[i] + suit] = freq
                elif "-" in part[3:]:
                    bits = part.split("-")
                    hi_card = bits[0][1]
                    lo_card = bits[1][1]
                    for i in range(RANK_IDX[lo_card], RANK_IDX[hi_card] + 1):
                        result[r1 + RANKS[i] + suit] = freq
        except Exception:
            continue
    return result


# === RFI (open) ranges by position ===
# Default frequencies are pure (1.0). Optuna can shift via tightness/aggression.
RFI_FREQS: Dict[str, Dict[str, float]] = {
    "LJ":  _expand_to_freq_dict("66+,A3s+,K8s+,Q9s+,J9s+,T9s,ATo+,KJo+,QJo"),
    "HJ":  _expand_to_freq_dict("55+,A2s+,K6s+,Q9s+,J9s+,T9s,98s,87s,76s,ATo+,KTo+,QTo+"),
    "CO":  _expand_to_freq_dict("33+,A2s+,K3s+,Q6s+,J8s+,T7s+,97s+,87s,76s,A8o+,KTo+,QTo+,JTo"),
    "BTN": _expand_to_freq_dict("22+,A2s+,K2s+,Q3s+,J4s+,T6s+,96s+,85s+,75s+,64s+,53s+,A4o+,K8o+,Q9o+,J9o+,T8o+,98o"),
    "SB":  _expand_to_freq_dict("22+,A2s+,K2s+,Q4s+,J6s+,T7s+,96s+,85s+,75s+,64s+,54s,A2o+,K7o+,Q8o+,J8o+,T8o+,98o"),
}


# === 3-bet & call ranges by (my_position, raiser_position) ===
THREEBET_FREQS: Dict[Tuple[str, str], Dict[str, float]] = {
    # In-position
    ("HJ", "LJ"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,KQs,KJs,KTs,AKo,AQo"),
    ("CO", "LJ"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,A4s,KQs,KJs,KTs,AKo,AQo"),
    ("CO", "HJ"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,A4s,KQs,KJs,KTs,AKo,AQo,AJo"),
    ("BTN", "LJ"): _expand_to_freq_dict("JJ+,AKs,AQs,AJs,A5s,A4s,KQs,AKo,AQo"),
    ("BTN", "HJ"): _expand_to_freq_dict("QQ+,AKs,AQs,AJs,A5s,A4s,KQs,KJs,AKo,AQo"),
    ("BTN", "CO"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,A4s,KQs,KJs,AKo,AQo,AJo"),
    # Out-of-position (SB)
    ("SB", "LJ"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,KQs,AKo,AQo"),
    ("SB", "HJ"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,A4s,KQs,AKo,AQo,AJo"),
    ("SB", "CO"): _expand_to_freq_dict("99+,AKs,AQs,AJs,ATs,A5s,A4s,KQs,KJs,AKo,AQo,AJo"),
    ("SB", "BTN"): _expand_to_freq_dict("88+,A9s+,A5s,A4s,KTs+,QTs+,JTs,AKo,AQo,AJo,KQo"),
    # BB
    ("BB", "LJ"): _expand_to_freq_dict("QQ+,AKs,A5s,AKo,AQs"),
    ("BB", "HJ"): _expand_to_freq_dict("JJ+,AKs,AQs,A5s,A4s,KQs,AKo,AQo"),
    ("BB", "CO"): _expand_to_freq_dict("TT+,AKs,AQs,AJs,A5s,A4s,KQs,AKo,AQo"),
    ("BB", "BTN"): _expand_to_freq_dict("99+,AKs,AQs,AJs,ATs,A5s,A4s,A3s,KQs,KJs,AKo,AQo,AJo,KQo"),
}


# === 3-bet calling ranges (when we don't 3-bet but defend) ===
THREEBET_CALL_FREQS: Dict[Tuple[str, str], Dict[str, float]] = {
    # BTN call ranges
    ("BTN", "LJ"): _expand_to_freq_dict("TT,99,88,77,76s,65s,54s,JTs,T9s,98s,QJs,KJs,KTs,ATs,QTs"),
    ("BTN", "HJ"): _expand_to_freq_dict("JJ-77,T9s,98s,87s,76s,JTs,QJs,KJs,KTs,ATs"),
    ("BTN", "CO"): _expand_to_freq_dict("99-66,T9s,98s,87s,76s,JTs,QJs,KTs"),
    # BB calling ranges (much wider - they get a discount)
    ("BB", "LJ"): _expand_to_freq_dict("22-JJ,A2s-AJs,K9s-KQs,Q9s+,J9s+,T9s,98s,87s,76s,65s,ATo+,KTo+,QTo+,JTo"),
    ("BB", "HJ"): _expand_to_freq_dict("22-TT,A2s-AJs,K8s-KJs,Q8s+,J8s+,T8s,97s+,86s+,75s+,65s,54s,A9o+,KTo+,QTo+,JTo"),
    ("BB", "CO"): _expand_to_freq_dict("22-99,A2s-ATs,K6s-KJs,Q6s+,J7s+,T7s+,96s+,85s+,75s+,65s,54s,43s,A7o+,K9o+,Q9o+,J9o+,T9o"),
    ("BB", "BTN"): _expand_to_freq_dict("22-88,A2s-A9s,K2s-KTs,Q2s+,J5s+,T5s+,95s+,84s+,74s+,63s+,53s+,42s+,32s,A2o-ATo,K6o-KJo,Q8o+,J8o+,T8o,97o+,87o,76o,65o"),
}


# === 4-bet and 5-bet ranges (value-heavy at 100bb) ===
FOURBET_VALUE_FREQS: Dict[str, float] = _expand_to_freq_dict("QQ+,AKs,AKo")
FOURBET_BLUFF_FREQS: Dict[str, float] = _expand_to_freq_dict("A5s,A4s")
FIVEBET_FREQS: Dict[str, float] = _expand_to_freq_dict("KK+,AKs")


# === Heads-up ranges (separate chart, big difference from 6-max) ===
HU_BTN_OPEN_FREQS: Dict[str, float] = _expand_to_freq_dict(
    "22+,A2s+,K2s+,Q2s+,J2s+,T2s+,93s+,82s+,72s+,62s+,52s+,42s+,32s,"
    "A2o+,K2o+,Q4o+,J5o+,T6o+,97o+,87o,76o,65o,54o"
)
HU_BB_3BET_FREQS: Dict[str, float] = _expand_to_freq_dict(
    "TT+,A9s+,A5s,A4s,KQs,KJs,QJs,JTs,AJo+,KQo"
)
HU_BB_CALL_FREQS: Dict[str, float] = _expand_to_freq_dict(
    "22-99,A2s-A8s,K2s-KJs,Q2s-QTs,J3s-JTs,T3s-T9s,93s-98s,83s-87s,73s-76s,"
    "63s-65s,53s-54s,A2o-ATo,K2o-KJo,Q4o-QTo,J5o-J9o,T6o-T9o,97o-98o,87o,76o"
)
HU_BTN_4BET_FREQS: Dict[str, float] = _expand_to_freq_dict("KK+,AKs,AKo")
HU_BB_5BET_FREQS: Dict[str, float] = _expand_to_freq_dict("KK+,AKs")


# Cached set of "tight monster" hands used in jam-or-fold spots.
TIGHT_MONSTERS = {"AA", "KK", "QQ", "AKs"}
PURE_MONSTERS = {"AA", "KK"}


# ============================================================================
# 5. HELPER FUNCTIONS (pure utilities, no decision logic)
# ============================================================================

def hand_str(hole_cards: List[str]) -> str:
    """Convert ['As', 'Kh'] -> 'AKo'. Pairs -> 'AA'. High card first."""
    if len(hole_cards) != 2:
        return ""
    r1, s1 = hole_cards[0][0], hole_cards[0][1]
    r2, s2 = hole_cards[1][0], hole_cards[1][1]
    if r1 == r2:
        return r1 + r2
    if RANK_IDX[r1] < RANK_IDX[r2]:
        r1, r2, s1, s2 = r2, r1, s2, s1
    suit = "s" if s1 == s2 else "o"
    return r1 + r2 + suit


def board_texture_features(board) -> dict:
    if not board:
        return {"paired": 0.0, "monotone": 0.0, "connected": 0.0, "high_card": 0.0}

    ranks = [c[0] for c in board]
    suits = [c[1] for c in board]

    rank_counts = {r: ranks.count(r) for r in set(ranks)}
    suit_counts = {s: suits.count(s) for s in set(suits)}

    paired = 1.0 if max(rank_counts.values()) >= 2 else 0.0
    monotone = (max(suit_counts.values()) - 1) / max(len(board) - 1, 1)  # 0 to 1

    # Connectedness: gap-distance between ranks normalized
    rank_idxs = sorted(RANK_IDX[r] for r in ranks)
    if len(rank_idxs) >= 2:
        spans = [rank_idxs[i+1] - rank_idxs[i] for i in range(len(rank_idxs)-1)]
        connected = max(0.0, 1.0 - (sum(spans) / (len(spans) * 4)))
    else:
        connected = 0.0

    high_card = max(RANK_IDX[r] for r in ranks) / 12.0  # 0 to 1

    return {
        "paired": paired,
        "monotone": monotone,
        "connected": connected,
        "high_card": high_card,
    }

def board_texture(board: List[str]) -> str:
    """Classify board: 'dry', 'wet', 'medium'."""
    if len(board) < 3:
        return "dry"
    ranks = [RANK_IDX[c[0]] for c in board]
    suits = [c[1] for c in board]
    suit_counts = {s: suits.count(s) for s in set(suits)}
    max_suit = max(suit_counts.values())
    sorted_r = sorted(ranks)
    gap = max(sorted_r) - min(sorted_r)
    has_pair = len(set(ranks)) < len(ranks)
    if max_suit >= 3:
        return "wet"
    if max_suit == 2 and gap <= 4:
        return "wet"
    if gap <= 4 and not has_pair:
        return "wet"
    if has_pair:
        return "dry"
    if gap >= 6 and max_suit < 2:
        return "dry"
    return "medium"


def safe_raise_amount(state: dict, target: int) -> int:
    """Clamp raise to legal bounds."""
    stack = state["your_stack"]
    bet_so_far = state["your_bet_this_street"]
    max_raise = stack + bet_so_far
    target = max(int(target), state["min_raise_to"])
    target = min(target, max_raise)
    return target


def stack_tightness(stack_bb: float, cfg: Config) -> float:
    """Returns multiplier for opening/3-bet frequencies based on stack depth.
    Smoothly interpolates from 1.0 at full stack to cfg.stack_short_tightness at shallow."""
    if stack_bb >= cfg.stack_full_threshold_bb:
        return 1.0
    if stack_bb <= cfg.stack_short_threshold_bb:
        return cfg.stack_short_tightness
    range_bb = cfg.stack_full_threshold_bb - cfg.stack_short_threshold_bb
    if range_bb <= 0:
        return 1.0
    ratio = (stack_bb - cfg.stack_short_threshold_bb) / range_bb
    return cfg.stack_short_tightness + ratio * (1.0 - cfg.stack_short_tightness)


def field_widening(n_active: int, cfg: Config) -> float:
    """Multiplier that widens ranges when fewer than 6 players are active.
    Returns 1.0 at full ring, scales up as field shrinks."""
    if n_active >= 6:
        return 1.0
    return 1.0 + cfg.shrink_widening_factor * (6 - n_active)


def stack_risked_pct(state: dict, owed: int) -> float:
    """Fraction of effective stack at risk if we call this bet."""
    stack = state["your_stack"]
    bet_so_far = state["your_bet_this_street"]
    total_invested_if_call = bet_so_far + owed
    starting_stack_estimate = stack + bet_so_far
    if starting_stack_estimate <= 0:
        return 1.0
    return min(1.0, total_invested_if_call / starting_stack_estimate)


def get_hand_rng(state: dict) -> random.Random:
    """Deterministic per-hand RNG. Same hand_id + same matchup = same decisions.
    This is what lets the harness's CRN testing cancel out our randomness."""
    hand_id = state.get("hand_id", "")
    seat = state.get("seat_to_act", 0)
    # Mix hand_id and seat so different seats see different randomness within a hand
    seed_str = f"{hand_id}:{seat}:{len(state.get('action_log', []))}"
    return random.Random(hash(seed_str) & 0xFFFFFFFF)


def lookup_freq(freq_dict: Dict[str, float], hand: str) -> float:
    """Get raise frequency for hand. Returns 0.0 if not in chart."""
    return freq_dict.get(hand, 0.0)


# ============================================================================
# 6. OPPONENT MODELLING
# ============================================================================

# Track per-opponent action features. Bayesian prior shrinks early-match noise.
class BehaviouralProfile:
    """Continuous behavioural features per opponent, with Beta-Binomial priors."""

    # (alpha, beta) priors — represent population belief, strength = alpha + beta
    PRIORS = {
        "vpip":              (6, 14),    # 30% prior
        "pfr":               (4, 16),    # 20% prior
        "three_bet":         (2, 18),    # 10% prior
        "fold_to_3bet":      (12, 8),    # 60% prior
        "fold_to_cbet_dry":  (12, 8),    # 60% prior
        "fold_to_cbet_wet":  (8, 12),    # 40% prior
        "fold_to_2nd_barrel":(10, 10),   # 50% prior
        "fold_to_3rd_barrel":(8, 12),    # 40% prior
        "donk":              (1, 19),    # 5% prior
        "check_raise":       (1, 19),    # 5% prior
    }

    def __init__(self, prior_weight: float = 15.0):
        # n_obs and n_pos are observation counts and positive counts per stat
        self.n_obs = {k: 0 for k in self.PRIORS}
        self.n_pos = {k: 0 for k in self.PRIORS}
        self.prior_weight_scale = prior_weight / 20.0

        # Postflop aggression tracking
        self.postflop_bets_raises = 0
        self.postflop_calls = 0

        # Sizing tracking — list of (bet_size / pot_at_decision) ratios
        self.bet_size_pcts = []

        # Showdowns: list of opponent's hand strength when shown
        self.showdown_ranks = []
        
        self.hands_observed = 0

    def stat(self, name: str) -> float:
        """Return Bayesian-estimated probability for this stat."""
        alpha, beta = self.PRIORS[name]
        alpha *= self.prior_weight_scale
        beta *= self.prior_weight_scale
        return (self.n_pos[name] + alpha) / (self.n_obs[name] + alpha + beta)

    def observe(self, name: str, was_positive: bool, count: int = 1):
        """Record observation(s) for a stat."""
        self.n_obs[name] += count
        if was_positive:
            self.n_pos[name] += count

    @property
    def wtsd_strength(self) -> float:
        """Mean normalized hand rank at showdown (0.0 to 1.0)."""
        if not self.showdown_ranks:
            return 0.5  # Neutral default
        return sum(self.showdown_ranks) / len(self.showdown_ranks)

    @property
    def aggression_factor(self) -> float:
        if self.postflop_calls == 0:
            return 1.0
        return self.postflop_bets_raises / max(self.postflop_calls, 1)

    @property
    def mean_bet_pct_pot(self) -> float:
        if not self.bet_size_pcts:
            return 0.66
        return sum(self.bet_size_pcts) / max(len(self.bet_size_pcts), 1)

INITIAL_STACK = 10000
our_match_delta = 0
from collections import defaultdict
OPPONENTS: dict = defaultdict(BehaviouralProfile)
PROCESSED_HANDS: set = set()

def update_opponents_from_log(state: dict):
    if state.get("type") != "hand_complete":
        return
        
    hand_id = state.get("hand_id", "")
    if hand_id in PROCESSED_HANDS:
        return
    PROCESSED_HANDS.add(hand_id)

    events = state.get("events", [])
    board = state.get("community_cards", [])
    flop_texture = board_texture(board[:3]) if len(board) >= 3 else "dry"
    
    for bot_id in state.get("final_stacks", {}):
        OPPONENTS[bot_id].hands_observed += 1

    pf_first_action = set()
    pf_aggressor = None
    last_bettor = None
    
    for ev in events:
        t = ev["type"]
        street = ev.get("street")

        if t == "showdown":
            revealed = ev.get("revealed_cards", {})
            if not revealed:
                continue
            
            # The board is complete at showdown
            if len(board) == 5 and HAVE_EVAL7:
                try:
                    eval7_board = [eval7.Card(c) for c in board]
                    for bot_id, hole in revealed.items():
                        if bot_id in OPPONENTS and len(hole) == 2:
                            eval7_hole = [eval7.Card(c) for c in hole]
                            # Use _equity_heuristic for 0.0 - 1.0 mapping, or we could just use the eval7 absolute score.
                            # The spec says "evaluate their hand rank with eval7 and append to showdown_ranks"
                            # Let's map it roughly: 0 to 7462 is the eval7 range. Higher is better.
                            score = eval7.evaluate(eval7_hole + eval7_board)
                            # Normalize it to 0-1
                            normalized = score / 7462.0
                            OPPONENTS[bot_id].showdown_ranks.append(normalized)
                except Exception:
                    pass
            continue
        
        if t == "street_start":
            last_bettor = None
            
        elif t == "action":
            bot_id = ev["bot_id"]
            action = ev["action"]
            opp = OPPONENTS[bot_id]
            
            # ALWAYS record bet/raise sizes for ALL streets
            if action in ("raise", "all_in"):
                pot = ev.get("pot", 0)
                if pot > 0:
                    sz = ev.get("amount", 0) / pot
                    opp.bet_size_pcts.append(sz)
            
            if street == "preflop":
                if bot_id not in pf_first_action:
                    pf_first_action.add(bot_id)
                    opp.observe("vpip", action != "fold")
                    if action in ("raise", "all_in"):
                        opp.observe("pfr", True)
                        pf_aggressor = bot_id
                        last_bettor = bot_id
                    else:
                        opp.observe("pfr", False)
                else:
                    if action in ("raise", "all_in"):
                        opp.observe("three_bet", True)
                        pf_aggressor = bot_id
                        last_bettor = bot_id
                    elif action == "fold" and last_bettor is not None:
                        opp.observe("fold_to_3bet", True)
                    elif action == "call" and last_bettor is not None:
                        opp.observe("fold_to_3bet", False)
                        
            else: # postflop
                if action in ("raise", "all_in", "call"):
                    opp.postflop_calls += (action == "call")
                    opp.postflop_bets_raises += (action in ("raise", "all_in"))
                    
                if action in ("raise", "all_in"):
                    if last_bettor is None:
                        if bot_id != pf_aggressor and pf_aggressor is not None:
                            opp.observe("donk", True)
                    else:
                        opp.observe("check_raise", True)

                    last_bettor = bot_id

                elif action == "fold" and last_bettor is not None:
                    if street == "flop" and last_bettor == pf_aggressor:
                        stat = "fold_to_cbet_dry" if flop_texture == "dry" else "fold_to_cbet_wet"
                        opp.observe(stat, True)
                    elif street == "turn" and last_bettor == pf_aggressor:
                        opp.observe("fold_to_2nd_barrel", True)
                    elif street == "river" and last_bettor == pf_aggressor:
                        opp.observe("fold_to_3rd_barrel", True)
                        
                elif action == "call" and last_bettor is not None:
                    if street == "flop" and last_bettor == pf_aggressor:
                        stat = "fold_to_cbet_dry" if flop_texture == "dry" else "fold_to_cbet_wet"
                        opp.observe(stat, False)
                    elif street == "turn" and last_bettor == pf_aggressor:
                        opp.observe("fold_to_2nd_barrel", False)
                    elif street == "river" and last_bettor == pf_aggressor:
                        opp.observe("fold_to_3rd_barrel", False)

def is_maniac(bot_id: str, cfg=None) -> bool:
    if bot_id not in OPPONENTS:
        return False
    p = OPPONENTS[bot_id]
    if p.n_obs["vpip"] < (cfg.maniac_min_sample if cfg else 6):
        return False
    raw_vpip = p.n_pos["vpip"] / p.n_obs["vpip"]
    raw_pfr = p.n_pos["pfr"] / max(p.n_obs["pfr"], 1)
    thresh_vpip = cfg.maniac_vpip_threshold if cfg else 0.52
    thresh_pfr = cfg.maniac_pfr_threshold if cfg else 0.40
    return raw_vpip > thresh_vpip and raw_pfr > thresh_pfr

def is_calling_station(bot_id: str, cfg=None) -> bool:
    if bot_id not in OPPONENTS:
        return False
    p = OPPONENTS[bot_id]
    if p.n_obs["vpip"] < (cfg.station_min_sample if cfg else 8):
        return False
    raw_vpip = p.n_pos["vpip"] / p.n_obs["vpip"]
    raw_pfr = p.n_pos["pfr"] / max(p.n_obs["pfr"], 1)
    thresh_vpip = cfg.station_vpip_threshold if cfg else 0.35
    thresh_pfr = cfg.station_pfr_threshold if cfg else 0.15
    return raw_vpip > thresh_vpip and raw_pfr < thresh_pfr

def is_unknown(bot_id: str, cfg) -> bool:
    if bot_id not in OPPONENTS:
        return True
    return OPPONENTS[bot_id].hands_observed < cfg.cold_start_threshold_hands

def any_active_maniac(state: dict, cfg) -> bool:
    log = state.get("action_log", [])
    me = state["seat_to_act"]
    for e in log:
        if e.get("action") in ("raise", "all_in") and e.get("seat") != me:
            seat = e["seat"]
            bot_id = next((p["bot_id"] for p in state["players"] if p["seat"] == seat), None)
            if bot_id and is_maniac(bot_id, cfg):
                return True
    return False

def any_active_unknown(state: dict, cfg) -> bool:
    me = state["seat_to_act"]
    for p in state["players"]:
        if p.get("seat") == me or p.get("is_folded"):
            continue
        if is_unknown(p["bot_id"], cfg):
            return True
    return False
# ============================================================================

def get_position_label(state: dict) -> str:
    """Compute position label: LJ/HJ/CO/BTN/SB/BB based on dealer derived from log."""
    n = len(state["players"])
    my_seat = state["seat_to_act"]
    log = state.get("action_log", [])

    bb_seat = sb_seat = None
    for entry in log:
        if entry.get("action") == "big_blind":
            bb_seat = entry["seat"]
        elif entry.get("action") == "small_blind":
            sb_seat = entry["seat"]

    if bb_seat is None:
        return "MP"

    if n == 2:
        return "BTN" if my_seat == sb_seat else "BB"

    btn_seat = (bb_seat - 2) % n
    offset = (my_seat - btn_seat) % n

    if n >= 6:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "LJ", 4: "HJ", 5: "CO"}.get(offset, "LJ")
    elif n == 5:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "HJ", 4: "CO"}.get(offset, "HJ")
    elif n == 4:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "CO"}.get(offset, "CO")
    elif n == 3:
        return {0: "BTN", 1: "SB", 2: "BB"}.get(offset, "BTN")
    return "MP"


def get_opp_position(state: dict, opp_seat: int) -> str:
    """Compute opponent's position label from their seat."""
    n = len(state["players"])
    log = state.get("action_log", [])
    bb_seat = sb_seat = None
    for entry in log:
        if entry.get("action") == "big_blind":
            bb_seat = entry["seat"]
        elif entry.get("action") == "small_blind":
            sb_seat = entry["seat"]
    if bb_seat is None:
        return "MP"
    if n == 2:
        return "BTN" if opp_seat == sb_seat else "BB"
    btn_seat = (bb_seat - 2) % n
    offset = (opp_seat - btn_seat) % n
    if n >= 6:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "LJ", 4: "HJ", 5: "CO"}.get(offset, "LJ")
    elif n == 5:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "HJ", 4: "CO"}.get(offset, "HJ")
    elif n == 4:
        return {0: "BTN", 1: "SB", 2: "BB", 3: "CO"}.get(offset, "CO")
    elif n == 3:
        return {0: "BTN", 1: "SB", 2: "BB"}.get(offset, "BTN")
    return "MP"


def count_aggressors(state: dict) -> int:
    """Count voluntary raisers/all-ins before us this hand (excluding us)."""
    log = state.get("action_log", [])
    me = state["seat_to_act"]
    return sum(1 for e in log
               if e.get("action") in ("raise", "all_in") and e.get("seat") != me)


def count_my_raises(state: dict) -> int:
    """Count how many times WE have raised in this hand."""
    log = state.get("action_log", [])
    me = state["seat_to_act"]
    return sum(1 for e in log
               if e.get("action") in ("raise", "all_in") and e.get("seat") == me)


def find_aggressor_seat(state: dict) -> Optional[int]:
    """Return seat of last aggressor before us, if any."""
    log = state.get("action_log", [])
    me = state["seat_to_act"]
    for e in reversed(log):
        if e.get("action") in ("raise", "all_in") and e.get("seat") != me:
            return e["seat"]
    return None


def preflop_scenario(state: dict) -> str:
    """Classify the preflop situation."""
    aggressors = count_aggressors(state)
    my_raises = count_my_raises(state)
    if aggressors == 0:
        return "open"
    if aggressors == 1 and my_raises == 0:
        return "face_open"
    if aggressors == 1 and my_raises == 1:
        return "face_3bet_as_raiser"
    if aggressors == 2 and my_raises == 0:
        return "face_3bet_cold"
    if aggressors == 2 and my_raises == 1:
        return "face_4bet_as_raiser"
    if my_raises >= 2:
        return "face_5bet_as_raiser"
    return "face_3bet_cold"


# ============================================================================
# 8. EQUITY CALCULATION
# ============================================================================

_EQUITY_CACHE: Dict[tuple, float] = {}


def _equity_heuristic(hole: List[str]) -> float:
    """Crude equity heuristic when eval7 unavailable."""
    r1 = RANK_IDX.get(hole[0][0], 0)
    r2 = RANK_IDX.get(hole[1][0], 0)
    pair = hole[0][0] == hole[1][0]
    suited = hole[0][1] == hole[1][1]
    high = max(r1, r2)
    if pair:
        return 0.50 + (high - 0) * 0.025
    base = 0.30 + (high - 0) * 0.012
    if suited:
        base += 0.04
    if abs(r1 - r2) <= 4:
        base += 0.02
    return min(base, 0.85)


def equity_vs_random(hole_cards: List[str], community_cards: List[str],
                     n_sims: int = 300, n_opp: int = 1) -> float:
    """Monte Carlo equity vs random opponent hand(s)."""
    if not HAVE_EVAL7:
        return _equity_heuristic(hole_cards)

    cache_key = (tuple(hole_cards), tuple(community_cards), n_opp)
    if cache_key in _EQUITY_CACHE:
        return _EQUITY_CACHE[cache_key]

    try:
        my_cards = [eval7.Card(c) for c in hole_cards]
        board = [eval7.Card(c) for c in community_cards]
        used = set(str(c) for c in my_cards + board)
        deck = [eval7.Card(r + s) for r in RANKS for s in "shdc" if (r + s) not in used]

        wins = ties = 0
        needed = 5 - len(board)
        for _ in range(n_sims):
            sample = random.sample(deck, 2 * n_opp + needed)
            opp_hands = [sample[i:i+2] for i in range(0, 2 * n_opp, 2)]
            full_board = board + sample[2 * n_opp:]
            my_score = eval7.evaluate(my_cards + full_board)
            opp_scores = [eval7.evaluate(h + full_board) for h in opp_hands]
            best_opp = max(opp_scores)
            if my_score > best_opp:
                wins += 1
            elif my_score == best_opp:
                ties += 1
        eq = (wins + ties / 2) / n_sims
    except Exception:
        eq = _equity_heuristic(hole_cards)

    _EQUITY_CACHE[cache_key] = eq
    return eq


def _hand_class_to_combos(hand_class: str, used: set) -> List[Tuple[str, str]]:
    """All card-combo pairs for a hand class like 'AKs' or 'TT'."""
    combos = []
    if len(hand_class) == 2:
        r = hand_class[0]
        suits = "shdc"
        for i in range(4):
            for j in range(i + 1, 4):
                c1, c2 = r + suits[i], r + suits[j]
                if c1 not in used and c2 not in used:
                    combos.append((c1, c2))
    elif len(hand_class) == 3:
        r1, r2, suit = hand_class[0], hand_class[1], hand_class[2]
        if suit == "s":
            for s in "shdc":
                c1, c2 = r1 + s, r2 + s
                if c1 not in used and c2 not in used:
                    combos.append((c1, c2))
        else:
            suits = "shdc"
            for s1 in suits:
                for s2 in suits:
                    if s1 == s2:
                        continue
                    c1, c2 = r1 + s1, r2 + s2
                    if c1 not in used and c2 not in used:
                        combos.append((c1, c2))
    return combos


def equity_vs_range(hole_cards: List[str], community_cards: List[str],
                    villain_range: Dict[str, float], n_sims: int = 300) -> float:
    """Monte Carlo equity vs a frequency-weighted range."""
    if not HAVE_EVAL7 or not villain_range:
        return equity_vs_random(hole_cards, community_cards, n_sims)

    try:
        my_cards = [eval7.Card(c) for c in hole_cards]
        board = [eval7.Card(c) for c in community_cards]
        used_str = set(str(c) for c in my_cards + board)
        deck_strs = [r + s for r in RANKS for s in "shdc" if (r + s) not in used_str]

        # Weight combos by frequency
        weighted_combos = []
        for hand_class, freq in villain_range.items():
            if freq <= 0:
                continue
            combos = _hand_class_to_combos(hand_class, used_str)
            for combo in combos:
                weighted_combos.append((combo, freq))

        if not weighted_combos:
            return equity_vs_random(hole_cards, community_cards, n_sims)

        wins = ties = 0
        needed = 5 - len(board)
        # Build weighted choice list
        weights = [w for _, w in weighted_combos]
        for _ in range(n_sims):
            v_combo, _ = random.choices(weighted_combos, weights=weights, k=1)[0]
            v_str = {v_combo[0], v_combo[1]}
            avail = [c for c in deck_strs if c not in v_str]
            if len(avail) < needed:
                continue
            extra = random.sample(avail, needed) if needed > 0 else []
            full_board = board + [eval7.Card(c) for c in extra]
            v_cards = [eval7.Card(c) for c in v_combo]
            my_score = eval7.evaluate(my_cards + full_board)
            v_score = eval7.evaluate(v_cards + full_board)
            if my_score > v_score:
                wins += 1
            elif my_score == v_score:
                ties += 1
        return (wins + ties / 2) / max(n_sims, 1)
    except Exception:
        return equity_vs_random(hole_cards, community_cards, n_sims)


def aggressor_likely_range(state: dict, agg_seat: int) -> Dict[str, float]:
    """Estimate aggressor's likely range based on position and action history."""
    agg_pos = get_opp_position(state, agg_seat)
    aggressors = count_aggressors(state)
    if aggressors == 1 and agg_pos in RFI_FREQS:
        return RFI_FREQS[agg_pos]
    if aggressors == 2:
        # 3-bet range: tight value
        return _expand_to_freq_dict("QQ+,AKs,AKo,A5s")
    return RFI_FREQS.get(agg_pos, RFI_FREQS["LJ"])


# ============================================================================
# 9. PREFLOP DECISION
# ============================================================================

def _effective_freq(base_freq: float, position: str, scenario: str,
                    stack_bb: float, n_active: int, cfg: Config) -> float:
    """Apply tightness/aggression/stack/field adjustments to a base chart frequency."""
    if base_freq <= 0:
        return 0.0

    pos_mult = getattr(cfg, f"pos_aggression_{position.lower()}", 1.0)
    stack_mult = stack_tightness(stack_bb, cfg)
    field_mult = field_widening(n_active, cfg)

    # Phase 7: Match Standing logic
    standing_modifier = math.tanh(cfg.k_standing * our_match_delta / INITIAL_STACK)
    standing_mult = 1.0

    if scenario == "open":
        scenario_mult = cfg.rfi_tightness
    elif scenario == "threebet":
        scenario_mult = cfg.threebet_tightness
        # Loosen 3-bet ranges when ahead (actually when behind, as standing_beta operates on it)
        # Spec: Loosen 3-bet ranges by `1 + standing_beta * standing_modifier` when ahead
        standing_mult = 1.0 + cfg.standing_beta * standing_modifier
    elif scenario == "fourbet":
        scenario_mult = cfg.fourbet_tightness
        # Tighten 4-bet ranges by `1 - standing_alpha * standing_modifier` when ahead
        standing_mult = 1.0 - cfg.standing_alpha * standing_modifier
    else:
        scenario_mult = 1.0

    return max(0.0, min(1.0, base_freq * pos_mult * stack_mult * field_mult * scenario_mult * standing_mult))


def passes_variance_check(state: dict, owed: int, hole: list, cfg: Config) -> bool:
    if owed <= 0:
        return True
    risk_pct = stack_risked_pct(state, owed)
    if risk_pct < 0.10:
        return True
    
    variance_term = cfg.variance_c * (risk_pct ** 2)
    if variance_term <= 0:
        return True
        
    pot = state["pot"]
    pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 1.0
    required_eq = pot_odds + variance_term
    eq = equity_vs_random(hole, [], n_sims=100)
    return eq >= required_eq

def decide_preflop_6max(state: dict, position: str, hand: str, cfg: Config,
                        rng: random.Random) -> dict:
    pot = state["pot"]
    owed = state["amount_owed"]
    can_check = state["can_check"]
    log = state.get("action_log", [])
    stack_bb = state["your_stack"] / BIG_BLIND
    n_active = sum(1 for p in state["players"] if not p.get("is_folded"))

    # === HEADS-UP BRANCH ===
    if n_active == 2:
        return decide_preflop_hu(state, position, hand, cfg, rng)

    scenario = preflop_scenario(state)
    # Apply variance penalty for preflop actions
    if not passes_variance_check(state, owed, state["your_cards"], cfg):
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    facing_maniac = any_active_maniac(state, cfg)
        
    opp_profile = None
    agg_seat = find_aggressor_seat(state)
    if agg_seat is not None:
        opp_id = next((p["bot_id"] for p in state["players"] if p["seat"] == agg_seat), None)
        if opp_id and opp_id in OPPONENTS:
            opp_profile = OPPONENTS[opp_id]

    # === SCENARIO: Open or check ===
    if scenario == "open":
        # If maniac at table, restrict to top of range
        if facing_maniac:
            tight_set = _expand_to_freq_dict("66+,AJs+,KQs,AQo+,AKo")
            base_freq = tight_set.get(hand, 0.0)
        else:
            base_freq = lookup_freq(RFI_FREQS.get(position, {}), hand)

        eff_freq = _effective_freq(base_freq, position, "open", stack_bb, n_active, cfg)
        if eff_freq > 0 and rng.random() < eff_freq:
            limpers = sum(1 for e in log if e.get("action") == "call")
            target = int(BIG_BLIND * (cfg.open_size_bb + limpers))
            return {"action": "raise", "amount": safe_raise_amount(state, target)}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # === SCENARIO: Facing a single open raise ===
    if scenario == "face_open":
        agg_seat = find_aggressor_seat(state)
        agg_pos = get_opp_position(state, agg_seat) if agg_seat is not None else "LJ"

        threebet_range = THREEBET_FREQS.get((position, agg_pos), {})
        call_range = THREEBET_CALL_FREQS.get((position, agg_pos), {})

        # Detect small-open exploitation
        current_bet = state["current_bet"]
        open_ratio = current_bet / BIG_BLIND  # e.g. 2.0 for min-raise, 2.5 for standard
        
        if open_ratio < cfg.small_open_threshold_bb:  # Small open detected
            call_freq_modifier = cfg.small_open_call_boost
            threebet_freq_modifier = cfg.small_open_3bet_boost
        else:
            call_freq_modifier = 1.0
            threebet_freq_modifier = 1.0

        # Exploit logic was moved to Bayesian priors in profile.stat() handling

        threebet_freq = lookup_freq(threebet_range, hand) * threebet_freq_modifier
        eff_3bet = _effective_freq(threebet_freq, position, "threebet", stack_bb, n_active, cfg)

        if eff_3bet > 0 and rng.random() < eff_3bet:
            ip = position in ("CO", "BTN")
            current = state["current_bet"]
            mult = cfg.threebet_size_ip if ip else cfg.threebet_size_oop
            target = int(current * mult)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}

        call_freq = lookup_freq(call_range, hand) * call_freq_modifier
        if call_freq == 0 and open_ratio < cfg.small_open_threshold_bb:
            eq = _equity_heuristic(state["your_cards"])
            required_eq = (owed / (pot + owed)) / cfg.small_open_call_boost
            if eq >= required_eq:
                call_freq = 1.0

        call_thresh = cfg.threebet_call_threshold_pct
        if opp_profile is not None:
            tb_rate = opp_profile.stat("three_bet")
            call_thresh *= 1.0 - cfg.k_tightness_vs_3bet_freq * max(0, tb_rate - 0.10)
        if call_freq > 0 and owed <= state["your_stack"] * call_thresh:
            return {"action": "call"}

        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # === SCENARIO: We opened, opp 3-bet us ===
    if scenario == "face_3bet_as_raiser":
        risk_pct = stack_risked_pct(state, owed)



        # Compute proposed 4-bet to check commit
        ip = position in ("CO", "BTN")
        current = state["current_bet"]
        mult = cfg.fourbet_size_ip if ip else cfg.fourbet_size_oop
        proposed_4bet = int(current * mult)
        chips_to_4bet = proposed_4bet - state["your_bet_this_street"]
        fourbet_risk = chips_to_4bet / max(state["your_stack"] + state["your_bet_this_street"], 1)

        # Jam-or-fold if 4-bet commits too much
        if fourbet_risk >= cfg.fourbet_commit_threshold:
            fivebet_freq = lookup_freq(FIVEBET_FREQS, hand)
            if fivebet_freq > 0 or hand in TIGHT_MONSTERS:
                return {"action": "all_in"}
            return {"action": "fold"}

        # Shallow stack jam-or-fold
        if stack_bb < cfg.shallow_jam_threshold_bb:
            fivebet_freq = lookup_freq(FIVEBET_FREQS, hand)
            if fivebet_freq > 0 or hand in TIGHT_MONSTERS:
                return {"action": "all_in"}
            return {"action": "fold"}

        # Standard 4-bet for value
        value_freq = lookup_freq(FOURBET_VALUE_FREQS, hand)
        eff_4bet = _effective_freq(value_freq, position, "fourbet", stack_bb, n_active, cfg)
        if opp_profile is not None:
            tb_rate = opp_profile.stat("three_bet")
            eff_4bet *= 1.0 + cfg.k_4bet_vs_3bet_freq * max(0, tb_rate - 0.10)
        if eff_4bet > 0 and rng.random() < eff_4bet:
            return {"action": "raise", "amount": safe_raise_amount(state, proposed_4bet)}

        # 4-bet bluff with blockers - not vs maniacs
        if not facing_maniac and ip:
            bluff_freq = lookup_freq(FOURBET_BLUFF_FREQS, hand)
            if bluff_freq > 0 and rng.random() < cfg.fourbet_bluff_freq:
                return {"action": "raise", "amount": safe_raise_amount(state, proposed_4bet)}

        # Value-call with strong-but-not-4-bet hands
        call_thresh = cfg.fourbet_call_threshold_pct
        if opp_profile is not None:
            tb_rate = opp_profile.stat("three_bet")
            call_thresh *= 1.0 - cfg.k_tightness_vs_3bet_freq * max(0, tb_rate - 0.10)
        if hand in {"JJ", "TT", "AKo", "AQs"} and owed <= state["your_stack"] * call_thresh:
            return {"action": "call"}

        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # === SCENARIO: We didn't open, two raisers in front (3-bet cold) ===
    if scenario == "face_3bet_cold":
        risk_pct = stack_risked_pct(state, owed)


        if hand in TIGHT_MONSTERS:
            return {"action": "all_in"}
        call_thresh_cold = cfg.threebet_call_threshold_pct
        if opp_profile is not None:
            tb_rate = opp_profile.stat("three_bet")
            call_thresh_cold *= 1.0 - cfg.k_tightness_vs_3bet_freq * max(0, tb_rate - 0.10)
        if hand in {"JJ", "AKo", "AQs"} and owed <= state["your_stack"] * call_thresh_cold:
            return {"action": "call"}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # === SCENARIO: Facing a 4-bet or 5-bet ===
    if scenario in ("face_4bet_as_raiser", "face_5bet_as_raiser"):
        risk_pct = stack_risked_pct(state, owed)

        if lookup_freq(FIVEBET_FREQS, hand) > 0 or hand in PURE_MONSTERS:
            return {"action": "all_in"}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    if can_check:
        return {"action": "check"}
    return {"action": "fold"}


def decide_preflop_hu(state: dict, position: str, hand: str, cfg: Config,
                      rng: random.Random) -> dict:
    """Heads-up preflop with separate ranges."""
    can_check = state["can_check"]
    # Apply variance penalty for preflop actions
    if not passes_variance_check(state, state["amount_owed"], state["your_cards"], cfg):
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}
    aggressors = count_aggressors(state)
    stack_bb = state["your_stack"] / BIG_BLIND

    if aggressors == 0:
        if position == "BTN":
            base_freq = lookup_freq(HU_BTN_OPEN_FREQS, hand)
            eff_freq = _effective_freq(base_freq, "BTN", "open", stack_bb, 2, cfg)
            if eff_freq > 0 and rng.random() < eff_freq:
                target = int(BIG_BLIND * cfg.open_size_bb)
                return {"action": "raise", "amount": safe_raise_amount(state, target)}
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}
        else:
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

    if aggressors == 1:
        # We're BB facing BTN open
        current_bet = state["current_bet"]
        open_ratio = current_bet / BIG_BLIND
        
        if open_ratio < cfg.small_open_threshold_bb:
            call_freq_modifier = cfg.small_open_call_boost
            threebet_freq_modifier = cfg.small_open_3bet_boost
        else:
            call_freq_modifier = 1.0
            threebet_freq_modifier = 1.0

        threebet_freq = lookup_freq(HU_BB_3BET_FREQS, hand) * threebet_freq_modifier
        eff_3bet = _effective_freq(threebet_freq, "BB", "threebet", stack_bb, 2, cfg)
        if eff_3bet > 0 and rng.random() < eff_3bet:
            target = int(current_bet * cfg.threebet_size_oop)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}

        call_freq = lookup_freq(HU_BB_CALL_FREQS, hand) * call_freq_modifier
        pot = state["pot"]
        owed = state["amount_owed"]
        if call_freq == 0 and open_ratio < cfg.small_open_threshold_bb:
            eq = _equity_heuristic(state["your_cards"])
            required_eq = (owed / (pot + owed)) / cfg.small_open_call_boost
            if eq >= required_eq:
                call_freq = 1.0

        if call_freq > 0 and owed <= state["your_stack"] * cfg.threebet_call_threshold_pct:
            return {"action": "call"}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    if aggressors == 2:
        fourbet_freq = lookup_freq(HU_BTN_4BET_FREQS, hand)
        eff_4bet = _effective_freq(fourbet_freq, "BTN", "fourbet", stack_bb, 2, cfg)
        if eff_4bet > 0 and rng.random() < eff_4bet:
            current = state["current_bet"]
            target = int(current * cfg.fourbet_size_ip)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}
        if hand in {"QQ", "JJ", "AKo", "AQs"}:
            return {"action": "call"}
        return {"action": "fold"}

    if lookup_freq(HU_BB_5BET_FREQS, hand) > 0 or hand in PURE_MONSTERS:
        return {"action": "all_in"}
    return {"action": "fold"}


# ============================================================================
# 10. POSTFLOP DECISION
# ============================================================================


def decide_river(state: dict, position: str, eq: float, opp_profile, cfg: Config, rng: random.Random) -> dict:
    """Phase 6: River-specific MDF and Value-to-Bluff branching."""
    pot = state["pot"]
    owed = state["amount_owed"]
    can_check = state["can_check"]
    stack = state["your_stack"]

    # 1. Facing a bet -> MDF logic
    if owed > 0:
        pot_before_bet = pot - owed
        bet_size = state["current_bet"]
        # Minimum Defense Frequency: 1 - (bet / (pot + bet))
        # Wait, standard MDF is pot_before_bet / (pot_before_bet + bet_size)
        # Using simple pot odds approximation for required top-% of range to defend:
        mdf = pot_before_bet / max(pot_before_bet + bet_size, 1)
        
        # Apply MDF aggression modifier (1.0 = strict MDF)
        defend_fraction = mdf * cfg.river_mdf_aggression
        
        # Are we in the top `defend_fraction` of our perceived river range?
        # A simple proxy: our absolute equity represents our percentile vs random hands.
        # This isn't perfect range-v-range but serves the architectural goal.
        required_eq = 1.0 - defend_fraction
        
        if eq >= required_eq:
            return {"action": "call"}
        return {"action": "fold"}

    # 2. Initiating / Checking -> V2B logic
    if eq >= cfg.river_value_strong_threshold:
        target = int(pot * cfg.river_value_strong_size)
        return {"action": "raise", "amount": safe_raise_amount(state, target)}
    elif eq >= cfg.river_value_thin_threshold:
        target = int(pot * cfg.river_value_thin_size)
        return {"action": "raise", "amount": safe_raise_amount(state, target)}

    # Are we bottom of range? (Bluffing candidate)
    if eq < 0.20:
        # Check blockers. For now, heuristics: do we have an Ace or King that didn't hit?
        # (Blocks their top pairs). 
        hole_ranks = [c[0] for c in state["your_cards"]]
        has_blocker = 'A' in hole_ranks or 'K' in hole_ranks
        
        # Base bluff freq is roughly 1 / (1 + V2B). We'll assume a half-pot target for bluffs.
        base_bluff_freq = 1.0 / (1.0 + cfg.river_v2b_half_pot)
        
        # Modify by blocker config
        if has_blocker:
            base_bluff_freq *= (1.0 + cfg.k_river_bluff_blocker)
        else:
            base_bluff_freq *= (1.0 - cfg.k_river_bluff_blocker)
            
        if rng.random() < base_bluff_freq:
            target = int(pot * 0.5)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}
            
    # Middle of range -> Check
    return {"action": "check"}

def decide_postflop(state: dict, position: str, cfg: Config,
                    rng: random.Random) -> dict:
    hole = state["your_cards"]
    board = state["community_cards"]
    pot = state["pot"]
    owed = state["amount_owed"]
    can_check = state["can_check"]
    stack = state["your_stack"]
    street = state["street"]
    log = state.get("action_log", [])
    me = state["seat_to_act"]

    # Were we the preflop aggressor?
    pf_log = [e for e in log if e.get("action") in ("raise", "all_in")]
    was_pf_aggressor = bool(pf_log) and pf_log[-1].get("seat") == me

    # Active opponent count
    n_opp = sum(1 for p in state["players"]
                if not p.get("is_folded") and p.get("seat") != me and not p.get("is_all_in"))
    n_opp = max(1, n_opp)

    # Sim count by street
    if street == "flop":
        n_sims = cfg.mc_sims_flop
    elif street == "turn":
        n_sims = cfg.mc_sims_turn
    else:
        n_sims = cfg.mc_sims_river

    # Equity
    agg_seat = find_aggressor_seat(state)
    if agg_seat is not None and len(log) > 4:
        v_range = aggressor_likely_range(state, agg_seat)
        eq = equity_vs_range(hole, board, v_range, n_sims=n_sims)
    else:
        eq = equity_vs_random(hole, board, n_sims=n_sims, n_opp=min(n_opp, 3))

    texture = board_texture(board)
    in_position = position in ("CO", "BTN")

    # Opponent profile
    facing_maniac = any_active_maniac(state, cfg)
    facing_station = False
    opp_profile = None
    opp_id = next((p["bot_id"] for p in state["players"]
                   if not p.get("is_folded") and p.get("seat") != me), None)
    if opp_id and opp_id in OPPONENTS:
        opp_profile = OPPONENTS[opp_id]
        
    if agg_seat is not None:
        agg_id = next((p["bot_id"] for p in state["players"] if p["seat"] == agg_seat), None)
        if agg_id and is_calling_station(agg_id, cfg):
            facing_station = True

    # Cold-start caution: only applied when FACING aggression, not when we initiate.
    # Adding it to value-betting thresholds was making us too passive in early hands.

    if street == "river":
        return decide_river(state, position, eq, opp_profile, cfg, rng)

    cold_caution_call = cfg.cold_start_caution if any_active_unknown(state, cfg) else 0.0

    # === Free check option ===
    if can_check:
        # Strong: bet for value (no cold caution - we're initiating, not calling)
        if eq >= cfg.equity_value_bet:
            sizing = cfg.sizing_value
            if opp_profile is not None:
                vpip = opp_profile.stat("vpip")
                sizing *= 1.0 + cfg.k_value_size_vs_station * max(0, vpip - 0.35)
            target = int(state["current_bet"] + pot * sizing)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}

        # PFR continuation bet (with multiway penalty)
        if was_pf_aggressor and street == "flop":
            tex = board_texture_features(board)
            cbet_freq = cfg.cbet_freq_base \
                      - cfg.k_texture_paired * tex["paired"] \
                      - cfg.k_texture_monotone * tex["monotone"] \
                      - cfg.k_texture_connected * tex["connected"] \
                      + cfg.k_texture_high_card * tex["high_card"]
            cbet_freq = max(0.0, min(1.0, cbet_freq))
            if opp_profile is not None:
                fold_rate = opp_profile.stat("fold_to_cbet_dry" if texture == "dry" else "fold_to_cbet_wet")
                cbet_freq *= 1.0 + cfg.k_bluff_vs_cbet_folder * (fold_rate - 0.5)
            # Multiway penalty
            cbet_freq *= cfg.cbet_multiway_penalty ** (n_opp - 1)
            # No bluff c-bets vs station
            if facing_station and eq < cfg.equity_thin_value:
                cbet_freq = 0.0
            if rng.random() < cbet_freq:
                target = int(state["current_bet"] + pot * cfg.cbet_size_pct)
                return {"action": "raise", "amount": safe_raise_amount(state, target)}

        # Turn & River barrels
        if was_pf_aggressor and street in ("turn", "river") and eq < cfg.equity_thin_value and not facing_station:
            barrel_freq = cfg.bluff_freq_ip if in_position else cfg.bluff_freq_oop
            if opp_profile is not None:
                if street == "turn":
                    fold_rate = opp_profile.stat("fold_to_2nd_barrel")
                    barrel_freq *= 1.0 + cfg.k_bluff_vs_2barrel_folder * (fold_rate - 0.5)
                else:
                    fold_rate = opp_profile.stat("fold_to_3rd_barrel")
                    barrel_freq *= 1.0 + cfg.k_bluff_vs_3barrel_folder * (fold_rate - 0.5)

                # Apply WTSD logic globally for turn/river bluffs
                barrel_freq *= 1.0 - cfg.k_bluff_vs_wtsd * (opp_profile.wtsd_strength - 0.5)

            if rng.random() < barrel_freq:
                target = int(state["current_bet"] + pot * cfg.sizing_thin)
                return {"action": "raise", "amount": safe_raise_amount(state, target)}

        # Thin value IP - not vs station with weak hand
        if eq >= cfg.equity_thin_value and in_position:
            target = int(state["current_bet"] + pot * cfg.sizing_thin)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}

        # Thin value OOP against passive opponents
        if not was_pf_aggressor and not in_position and eq > cfg.oop_passive_value_threshold:
            if opp_profile is not None and opp_profile.aggression_factor < cfg.passive_aggression_threshold:
                target = int(state["current_bet"] + pot * cfg.oop_passive_value_size)
                return {"action": "raise", "amount": safe_raise_amount(state, target)}

        # Bluff - never vs station
        if facing_station:
            return {"action": "check"}
        bluff_freq = cfg.bluff_freq_ip if in_position else cfg.bluff_freq_oop
        if opp_profile is not None:
            bluff_freq *= 1.0 - cfg.k_bluff_vs_wtsd * (opp_profile.wtsd_strength - 0.5)

        if eq < cfg.equity_thin_value and rng.random() < bluff_freq:
            target = int(state["current_bet"] + pot * cfg.sizing_thin)
            return {"action": "raise", "amount": safe_raise_amount(state, target)}

        return {"action": "check"}

    # === Facing a bet ===
    if owed <= 0:
        return {"action": "check"}

    pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 1.0
    risk_pct = stack_risked_pct(state, owed)



    # === Variance Penalty ===
    variance_term = cfg.variance_c * (risk_pct ** 2)
    required_eq = pot_odds + cfg.pot_odds_buffer_normal + variance_term + cold_caution_call

    if eq >= cfg.equity_raise_threshold and not facing_maniac:
        sizing = cfg.sizing_value
        if opp_profile is not None:
            vpip = opp_profile.stat("vpip")
            sizing *= 1.0 + cfg.k_value_size_vs_station * max(0, vpip - 0.35)
        target = int(state["current_bet"] + (pot + owed) * sizing)
        return {"action": "raise", "amount": safe_raise_amount(state, target)}

    if eq >= required_eq:
        return {"action": "call"}

    # SPR Commitment Regime
    spr = stack / max(pot, 1)
    commitment_factor = 1.0 / (1.0 + math.exp((spr - cfg.spr_commit_threshold) / cfg.spr_smoothness))

    if eq >= (cfg.equity_value_bet - cfg.k_commit * commitment_factor) and variance_term <= 0:
        return {"action": "call"}

    call_thresh = cfg.equity_call_threshold
    if opp_profile is not None:
        aggression = opp_profile.aggression_factor
        call_thresh *= 1.0 + cfg.k_call_threshold_vs_aggression * (aggression - 1.0)

    # Phase 7: Tighten thin-margin calls when ahead
    standing_modifier = math.tanh(cfg.k_standing * our_match_delta / INITIAL_STACK)
    call_thresh_modifier = 1.0 - cfg.standing_alpha * standing_modifier
    call_thresh *= call_thresh_modifier

    if eq >= (call_thresh - cfg.k_commit * commitment_factor) and owed <= pot * cfg.pot_odds_buffer_marginal and variance_term <= 0:
        return {"action": "call"}

    return {"action": "fold"}


# ============================================================================
# 11. MAIN ENTRY POINT
# ============================================================================

def decide(game_state: dict) -> dict:
    """Engine entry. Must return within 2 seconds."""
    global _EQUITY_CACHE, our_match_delta
    _EQUITY_CACHE = {}
    t0 = time.time()
    
    # Update match standing
    if "your_stack" in game_state:
        # Update match standing accurately by adding chips invested this hand
        invested = sum(evt.get("amount", 0) for evt in game_state.get("action_log", [])
                       if evt.get("seat") == game_state.get("seat_to_act"))
        our_match_delta = game_state["your_stack"] + invested - INITIAL_STACK

    try:
        try:
            update_opponents_from_log(game_state)
        except Exception:
            pass

        position = get_position_label(game_state)
        hand = hand_str(game_state["your_cards"])
        street = game_state["street"]
        rng = get_hand_rng(game_state)

        if street == "preflop":
            action = decide_preflop_6max(game_state, position, hand, CONFIG, rng)
        else:
            action = decide_postflop(game_state, position, CONFIG, rng)

        if time.time() - t0 > CONFIG.time_budget_sec:
            return {"action": "check"} if game_state.get("can_check") else {"action": "fold"}

        return action

    except Exception:
        if game_state.get("can_check"):
            return {"action": "check"}
        if game_state.get("amount_owed", 999) <= game_state.get("pot", 0) * 0.10:
            return {"action": "call"}
        return {"action": "fold"}
