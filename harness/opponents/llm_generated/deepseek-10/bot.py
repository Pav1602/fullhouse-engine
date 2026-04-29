"""
Opponent‑modeling bot for the Fullhouse Engine
Tracks VPIP (Voluntarily Put $ In Pot) and PFR (Preflop Raise) for every opponent,
then uses statistical profiles to adapt strategy.
"""

import eval7
from typing import Dict, List, Tuple, Optional

# ---------- GLOBAL OPPONENT STATISTICS ----------
# player_name -> { "hands": int, "vpip": int, "pfr": int }
player_stats: Dict[str, Dict[str, int]] = {}

# Per‑hand tracking (reset at the start of each hand)
hand_in_progress = False
hand_vpip_flags: Dict[str, bool] = {}   # VPIP already counted this hand?
hand_pfr_flags: Dict[str, bool] = {}    # PFR already counted this hand?
last_action_log_len = 0

# ---------- HELPER FUNCTIONS ----------

def is_vpip_preflop(action: dict, street: str) -> bool:
    """Return True if this action voluntarily adds chips preflop."""
    if street != "preflop":
        return False
    act = action.get("action", "")
    # "call", "raise", "all_in" are voluntary; blind postings are not
    return act in ("call", "raise", "all_in")

def is_pfr_preflop(action: dict, street: str) -> bool:
    """Return True if this action is a preflop raise."""
    if street != "preflop":
        return False
    act = action.get("action", "")
    # count both "raise" and "all_in" as a raise (imperfect but simple)
    return act in ("raise", "all_in")

def get_player_vpip_pfr(name: str) -> Tuple[float, float]:
    """Return (VPIP%, PFR%) for a player, or a default (20,15) for unknown."""
    stats = player_stats.get(name)
    if not stats or stats["hands"] < 5:
        return 20.0, 15.0   # default TAG
    vpip = stats["vpip"] / stats["hands"] * 100
    pfr = stats["pfr"] / stats["hands"] * 100
    return vpip, pfr

def classify_opponent(name: str) -> str:
    """Classify opponent based on VPIP/PFR."""
    vpip, pfr = get_player_vpip_pfr(name)
    if vpip > 35:
        return "loose" if pfr < 15 else "LAG"
    elif vpip < 20:
        return "tight" if pfr < 10 else "TAG"
    else:
        return "passive" if pfr < 10 else "normal"

def avg_opponent_aggression(names: List[str]) -> float:
    """Average PFR of the given player names."""
    if not names:
        return 15.0
    total = 0.0
    for name in names:
        _, pfr = get_player_vpip_pfr(name)
        total += pfr
    return total / len(names)

# ---------- PREFLOP HAND STRENGTH (simplified) ----------
# Sklansky‑Chubukov rank groups (1 = strongest)
# We assign each of the 169 possible starting hands a tier (1‑3)
def preflop_hand_tier(your_cards: List[str]) -> int:
    """
    Return 1 (premium: top ~5%), 2 (good: top ~15%), 3 (playable: top ~30%), 4 (garbage).
    Uses a quick rank mapping.
    """
    if len(your_cards) != 2:
        return 4
    # Normalize cards: rank first (2‑14), suited boolean
    ranks = [card[0] for card in your_cards]  # e.g., "A", "T"
    suited = your_cards[0][1] == your_cards[1][1]

    # Convert to numeric rank 2-14
    rank_map = {str(n): n for n in range(2, 10)}
    rank_map.update({"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14})
    try:
        r1, r2 = rank_map[ranks[0]], rank_map[ranks[1]]
    except KeyError:
        return 4

    # Sort high‑low
    high, low = max(r1, r2), min(r1, r2)
    pair = high == low

    # Tier classification (hand‑crafted)
    if pair:
        if high >= 10:          # JJ+
            return 1
        if high >= 7:           # 77‑TT
            return 2
        return 3                # 66-
    # Unpaired
    if suited:
        if high == 14:
            if low >= 10:       # AJs+
                return 1
            if low >= 8:        # ATs, A9s, A8s
                return 2
            return 3
        if high == 13 and low >= 10:  # KQs, KJs
            return 2
        if high == 13 and low == 9:   # K9s
            return 3
        if high == 12 and low >= 10:  # QJs
            return 2
        if high == 11 and low >= 9:   # JTs, J9s
            return 3
        if (high == 10 and low == 9) or (high == 9 and low == 8):  # T9s, 98s
            return 3
        return 4
    else:  # off‑suit
        if high == 14:
            if low >= 11:       # AQo+
                return 1
            if low >= 9:        # ATo+
                return 2
            return 3
        if high == 13 and low >= 11:  # KQo
            return 2
        if high == 13 and low == 10:  # KJo
            return 3
        if high == 12 and low >= 11:  # QJo
            return 3
        return 4

# ---------- POSTFLOP STRENGTH (using eval7) ----------
def hand_strength_postflop(hole: List[str], board: List[str]) -> int:
    """
    Return the absolute hand rank from eval7.
    Lower is stronger (1 = royal flush, 7462 = worst).
    """
    all_cards = hole + board
    return eval7.evaluate([eval7.Card(c) for c in all_cards])

def postflop_category(rank: int, board_len: int) -> str:
    """
    Map an absolute eval7 rank to "strong", "medium", "weak"
    depending on street.
    """
    # Thresholds tuned empirically for flop/turn/river.
    # Lower rank = better hand.
    if board_len == 3:   # flop
        if rank <= 2000:     # two‑pair or better, top pair top kicker
            return "strong"
        elif rank <= 4500:   # any pair, decent draw
            return "medium"
        else:
            return "weak"
    elif board_len == 4:   # turn
        if rank <= 1500:
            return "strong"
        elif rank <= 4000:
            return "medium"
        else:
            return "weak"
    else:                  # river
        if rank <= 1000:
            return "strong"
        elif rank <= 3500:
            return "medium"
        else:
            return "weak"

# ---------- MAIN DECISION FUNCTION ----------
def decide(game_state: dict) -> dict:
    global player_stats, hand_in_progress, hand_vpip_flags, hand_pfr_flags, last_action_log_len

    # Extract game info
    your_cards = game_state["your_cards"]
    community_cards = game_state["community_cards"]
    street = game_state["street"]
    pot = game_state["pot"]
    your_stack = game_state["your_stack"]
    amount_owed = game_state["amount_owed"]
    can_check = game_state["can_check"]
    current_bet = game_state["current_bet"]
    min_raise_to = game_state["min_raise_to"]
    players = game_state["players"]
    action_log = game_state["action_log"]

    # Identify our own name (not explicitly given, but we can find it)
    # Assume 'your_name' is in game_state if available, else fallback
    your_name = game_state.get("your_name", "hero")
    # If not provided, try to deduce from 'you' in players (not implemented)

    # ---------- OPPONENT STATS UPDATING ----------
    # Start of a new hand detection
    if street == "preflop" and len(action_log) == 0:
        # Finalize previous hand stats (handled by per‑hand reset)
        hand_in_progress = True
        hand_vpip_flags.clear()
        hand_pfr_flags.clear()
        last_action_log_len = 0

        # Increment "hands" for every active player
        for p in players:
            name = p.get("name", "")
            if not name:
                continue
            # Consider player active if stack > 0 (adjust for sit‑outs if needed)
            if p.get("stack", 0) > 0:
                if name not in player_stats:
                    player_stats[name] = {"hands": 0, "vpip": 0, "pfr": 0}
                player_stats[name]["hands"] += 1
                hand_vpip_flags[name] = False
                hand_pfr_flags[name] = False
    elif not hand_in_progress:
        # Edge case: we missed the start (first action arrives later).
        # Initialise now and process any existing actions.
        hand_in_progress = True
        hand_vpip_flags.clear()
        hand_pfr_flags.clear()
        for p in players:
            name = p.get("name", "")
            if not name or p.get("stack", 0) <= 0:
                continue
            if name not in player_stats:
                player_stats[name] = {"hands": 0, "vpip": 0, "pfr": 0}
            player_stats[name]["hands"] += 1
            hand_vpip_flags[name] = False
            hand_pfr_flags[name] = False
        # Process everything we already missed (all actions so far belong to the current street)
        for act in action_log:
            pname = act.get("player", "")
            if is_vpip_preflop(act, street) and not hand_vpip_flags.get(pname, True):
                hand_vpip_flags[pname] = True
                player_stats[pname]["vpip"] += 1
            if is_pfr_preflop(act, street) and not hand_pfr_flags.get(pname, True):
                hand_pfr_flags[pname] = True
                player_stats[pname]["pfr"] += 1
        last_action_log_len = len(action_log)

    # Process new actions since last observation
    for act in action_log[last_action_log_len:]:
        pname = act.get("player", "")
        if is_vpip_preflop(act, street) and not hand_vpip_flags.get(pname, True):
            hand_vpip_flags[pname] = True
            player_stats[pname]["vpip"] += 1
        if is_pfr_preflop(act, street) and not hand_pfr_flags.get(pname, True):
            hand_pfr_flags[pname] = True
            player_stats[pname]["pfr"] += 1
    last_action_log_len = len(action_log)

    # ---------- SITUATION ANALYSIS ----------
    # Identify opponents still in the hand
    active_opponents = []
    for p in players:
        if p.get("name") == your_name:
            continue
        # Active means not folded, not all‑in? For simplicity, stack > 0 and status not folded
        status = p.get("status", "active")
        if status in ("active", "all_in"):  # all_in still active, but we may ignore
            active_opponents.append(p["name"])

    # Basic pot odds
    pot_odds = amount_owed / (pot + amount_owed) if amount_owed > 0 else 0
    # Stack‑to‑pot ratio (simplified)
    spr = your_stack / pot if pot > 0 else float("inf")

    # ---------- PREFLOP STRATEGY ----------
    if street == "preflop":
        tier = preflop_hand_tier(your_cards)

        # Get average VPIP of active opponents (if any)
        avg_vpip = 20.0
        if active_opponents:
            vpip_list = [get_player_vpip_pfr(name)[0] for name in active_opponents]
            avg_vpip = sum(vpip_list) / len(vpip_list)

        # Adjust opening range based on opponent looseness
        if amount_owed == 0:  # no one raised yet
            if can_check:  # we are in BB and no raise
                # Check with weak hands, raise with strong hands
                if tier <= 2:  # strong enough to raise
                    raise_amt = min_raise_to if min_raise_to > 0 else pot
                    # Scale raise size based on opponent VPIP (bigger vs loose)
                    if avg_vpip > 40:
                        raise_amt = min_raise_to * 1.5
                    return {"action": "raise", "amount": int(raise_amt)}
                else:
                    return {"action": "check"}
            else:  # opening the pot from non‑BB position
                # Default open range: tier 1‑2 always open, tier 3 if opponents are tight
                if tier <= 2 or (tier == 3 and avg_vpip < 25):
                    # Open raise
                    raise_size = min_raise_to if min_raise_to > 0 else 3 * (current_bet or 2)  # rough
                    return {"action": "raise", "amount": int(raise_size)}
                else:
                    return {"action": "fold"}
        else:  # facing a raise
            # Get PFR of the raiser (first opponent who raised)
            raiser_name = None
            for a in reversed(action_log):
                if a.get("action") in ("raise", "all_in"):
                    raiser_name = a.get("player")
                    break
            raiser_pfr = 15.0
            if raiser_name:
                _, raiser_pfr = get_player_vpip_pfr(raiser_name)

            # Decision based on hand strength and raiser aggression
            if tier == 1:  # premium
                # Always 3‑bet
                reraise_to = max(min_raise_to, amount_owed * 2.5)
                return {"action": "raise", "amount": int(reraise_to)}
            elif tier == 2:  # good hand
                if raiser_pfr > 25:  # raiser is aggressive – call, maybe 3‑bet light
                    if spr > 10:
                        return {"action": "raise", "amount": int(min_raise_to)}
                    else:
                        return {"action": "call"}
                else:  # tight raiser – be cautious
                    if spr > 15:
                        return {"action": "call"}
                    else:
                        return {"action": "fold"}
            elif tier == 3:  # playable
                if raiser_pfr > 30 and pot_odds < 0.3:
                    return {"action": "call"}
                else:
                    return {"action": "fold"}
            else:
                return {"action": "fold"}

    # ---------- POSTFLOP STRATEGY ----------
    else:
        # Evaluate hand strength
        rank = hand_strength_postflop(your_cards, community_cards)
        cat = postflop_category(rank, len(community_cards))
        aggression = avg_opponent_aggression(active_opponents)

        # Determine if we are first to act (no bet yet)
        facing_bet = amount_owed > 0

        if not facing_bet:
            # We can check or bet
            if cat == "strong":
                # Value bet, size depends on board texture and opponent looseness
                if aggression > 25:  # aggressive opponents may call larger bets
                    bet = int(pot * 0.75)
                else:
                    bet = int(pot * 0.5)
                bet = max(bet, min_raise_to if min_raise_to else current_bet + 1)
                return {"action": "raise", "amount": bet}
            elif cat == "medium":
                # Check back or small probe bet vs passive opponents
                if aggression < 15:  # passive opponents – take a stab
                    bet = int(pot * 0.4)
                    if your_stack > bet * 3:
                        return {"action": "raise", "amount": bet}
                return {"action": "check"}
            else:  # weak
                # Bluff occasionally vs tight opponents
                if aggression < 20 and can_check:
                    # Semi‑bluff only if there is some equity (draw) – not implemented
                    return {"action": "check"}
                return {"action": "check"} if can_check else {"action": "fold"}  # safety
        else:
            # Facing a bet
            # If strong, raise
            if cat == "strong":
                # Raise for value
                raise_to = max(min_raise_to, int(amount_owed * 2.5))
                return {"action": "raise", "amount": raise_to}
            elif cat == "medium":
                # Call if pot odds are decent, opponent may be bluffing
                if pot_odds < 0.3 or aggression > 25:
                    return {"action": "call"}
                else:
                    return {"action": "fold"}
            else:
                # Weak hand – fold unless minimal bet and opponent is bluffy
                if amount_owed <= your_stack * 0.1 and aggression > 30:
                    return {"action": "call"}
                return {"action": "fold"}

    # Fallback
    return {"action": "check"} if can_check else {"action": "fold"}