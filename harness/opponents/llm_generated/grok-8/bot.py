import eval7
import random
from typing import Dict, Any

# Simple preflop hand categories (expandable)
PREflop_RANGES = {
    "early": ["AA", "KK", "QQ", "JJ", "TT", "99", "88", "AKs", "AQs", "AJs", "KQs", "AKo"],  # ~10-12%
    "middle": ["AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "AKs", "AQs", "AJs", "ATs", "KQs", "KJs", "QJs", "AKo", "AQo"],
    "late": ["AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "55", "AKs", "AQs", "AJs", "ATs", "A9s", "A8s",
             "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "AKo", "AQo", "AJo", "KQo"]  # wider on button
}

def hand_to_str(cards: list[str]) -> str:
    """Convert ['As', 'Kh'] to 'AKs' or 'AKo'"""
    if not cards or len(cards) != 2:
        return ""
    c1, c2 = sorted(cards, key=lambda x: "23456789TJQKA".index(x[0]), reverse=True)
    rank1, suit1 = c1[0], c1[1]
    rank2, suit2 = c2[0], c2[1]
    suited = "s" if suit1 == suit2 else "o"
    return rank1 + rank2 + suited

def is_in_range(hand_str: str, position: str) -> bool:
    pos_key = "early" if position in ["UTG", "UTG+1", "UTG+2"] else "middle" if position in ["LJ", "HJ"] else "late"
    range_list = PREflop_RANGES.get(pos_key, PREflop_RANGES["late"])
    return any(hand_str.startswith(r[:-1]) and (hand_str.endswith(r[-1]) or r[-1] in "so") for r in range_list)  # rough match

def get_position(game_state: dict) -> str:
    """Rough position based on seats. Improve with full player list if needed."""
    # Simple: assume standard 6-max or 9-max logic. For now, use button/dealer info if available.
    # game_state may have 'button' or seat indices. Fallback to "late" if unknown.
    return "late"  # Placeholder - enhance with actual seat calculation from total_players and your index

def evaluate_hand_strength(your_cards: list, community: list) -> float:
    """Return approximate hand strength (0-1) using eval7."""
    try:
        all_cards = [eval7.Card(c) for c in your_cards + community]
        our_rank = eval7.evaluate(all_cards)
        # Monte Carlo equity approximation (fast enough for 2s limit)
        deck = eval7.Deck()
        for c in all_cards:
            deck.cards.remove(c)
        wins = 0
        trials = 500 if len(community) >= 3 else 200  # fewer trials early
        for _ in range(trials):
            deck.shuffle()
            opp_cards = deck.deal(2)
            opp_rank = eval7.evaluate(all_cards[:len(your_cards)] + list(opp_cards) + community)  # wait, correct way:
            # Better: full 7-card for us vs random opp
            # Simplified: compare our 7-card rank to random opp 7-card
            opp_hand = opp_cards + [eval7.Card(c) for c in community]
            opp_rank = eval7.evaluate(opp_hand[:7] if len(opp_hand) > 7 else opp_hand)
            if our_rank > opp_rank:
                wins += 1
            elif our_rank == opp_rank:
                wins += 0.5
        return wins / trials
    except:
        return 0.5  # neutral on error

def decide(game_state: dict) -> dict:
    your_cards = game_state.get("your_cards", [])
    community = game_state.get("community_cards", [])
    street = game_state.get("street", "preflop")
    pot = game_state.get("pot", 0)
    your_stack = game_state.get("your_stack", 1000)
    amount_owed = game_state.get("amount_owed", 0)
    can_check = game_state.get("can_check", False)
    min_raise_to = game_state.get("min_raise_to", 0)
    current_bet = game_state.get("current_bet", 0)
    total_players = len(game_state.get("total players", []))  # or however it's keyed

    if not your_cards:
        return {"action": "fold"}

    hand_str = hand_to_str(your_cards)
    position = get_position(game_state)  # Enhance this

    # === Preflop ===
    if street == "preflop":
        if amount_owed == 0:  # Can open or check (but avoid limp)
            if is_in_range(hand_str, position):
                raise_amount = max(min_raise_to, int(pot * 3) + current_bet)  # 3x pot-ish open
                if raise_amount > your_stack:
                    return {"action": "all_in"}
                return {"action": "raise", "amount": raise_amount}
            else:
                return {"action": "fold"}  # Tight - fold marginal

        # Facing raise
        if amount_owed > 0:
            equity = evaluate_hand_strength(your_cards, community)  # preflop equity rough
            pot_odds = amount_owed / (pot + amount_owed)
            if equity > pot_odds * 1.3 or "AA KK QQ JJ AK".find(hand_str[:2]) != -1:  # Premiums 3-bet
                raise_amount = max(min_raise_to, int((pot + amount_owed) * 3.5))
                if raise_amount > your_stack * 0.8:
                    return {"action": "all_in"}
                return {"action": "raise", "amount": raise_amount}
            elif equity > pot_odds * 1.1:
                return {"action": "call"}
            else:
                return {"action": "fold"}

    # === Postflop ===
    hand_strength = evaluate_hand_strength(your_cards, community)
    is_aggressor = any(a.get("action") == "raise" and a.get("player") == "us" for a in game_state.get("action_log", []))  # rough

    to_call = amount_owed
    pot_after_call = pot + to_call

    if can_check:
        # Check or bet
        if hand_strength > 0.75 or (hand_strength > 0.6 and is_aggressor):  # Strong value or c-bet
            bet_size = max(min_raise_to, int(pot * 0.6))  # ~60% pot c-bet/value
            if bet_size > your_stack:
                return {"action": "all_in"}
            return {"action": "raise", "amount": bet_size + current_bet}  # total bet amount
        else:
            return {"action": "check"}

    else:
        # Facing bet
        pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 1
        if hand_strength > pot_odds * 1.5 or hand_strength > 0.85:  # Good pot odds or monster
            if hand_strength > 0.9 and your_stack > to_call * 3:
                # Raise for value
                raise_amount = max(min_raise_to, int((pot + to_call) * 2.5))
                if raise_amount > your_stack:
                    return {"action": "all_in"}
                return {"action": "raise", "amount": raise_amount}
            return {"action": "call"}
        elif hand_strength > 0.55 and random.random() < 0.25:  # Semi-bluff float/raise sometimes
            if min_raise_to > 0:
                return {"action": "raise", "amount": max(min_raise_to, int(pot * 2))}
            return {"action": "call"}
        else:
            return {"action": "fold"}

    # Default safe
    return {"action": "fold"}