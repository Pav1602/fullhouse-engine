import eval7
import random
from typing import Dict, Any

# Precomputed or simple preflop ranges (you can expand this heavily)
PREflop_RAISE_HANDS = {
    'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55',
    'AKs', 'AQs', 'AJs', 'ATs', 'A9s', 'A8s', 'A7s', 'A6s', 'A5s',
    'KQs', 'KJs', 'KTs', 'QJs', 'QTs', 'JTs',
    'AKo', 'AQo', 'AJo', 'ATo', 'KQo'
}


def card_to_eval7(card: str) -> eval7.Card:
    """Convert string like 'As' to eval7.Card"""
    return eval7.Card(card)


def get_hand_strength(my_cards: list, community: list) -> tuple:
    """Return (hand_rank, equity_estimate)"""
    all_cards = [card_to_eval7(c) for c in my_cards + community]

    if len(all_cards) >= 5:
        # Exact evaluation for made hand
        rank = eval7.evaluate(all_cards)
        hand_type = eval7.handtype(rank)
    else:
        rank = 0
        hand_type = "Preflop"

    # Simple Monte Carlo equity (fast version - limit iterations)
    equity = estimate_equity(my_cards, community, num_sim=800)

    return rank, equity, hand_type


def estimate_equity(hero_cards: list[str], board: list[str], num_sim: int = 600) -> float:
    """Monte Carlo equity estimation against random opponent hand"""
    hero = [card_to_eval7(c) for c in hero_cards]
    board_cards = [card_to_eval7(c) for c in board]
    deck = eval7.Deck()

    # Remove known cards
    for c in hero + board_cards:
        deck.cards.remove(c)

    wins = 0
    trials = 0

    for _ in range(num_sim):
        trials += 1
        deck.shuffle()
        opp = deck.deal(2)

        hero_best = eval7.evaluate(hero + board_cards)
        opp_best = eval7.evaluate(opp + board_cards)

        if hero_best > opp_best:
            wins += 1
        elif hero_best == opp_best:
            wins += 0.5  # tie

    return wins / trials if trials > 0 else 0.5


def get_position(game_state: dict) -> str:
    """Simple position: early, middle, late, button"""
    # This is approximate - improve by parsing seats and button
    num_players = len(game_state.get('total_players', []))
    # For now, use a heuristic based on action_log or assume late if few players left
    return "late" if num_players <= 4 else "middle"


def decide(game_state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        your_cards = game_state["your_cards"]
        community = game_state.get("community_cards", [])
        street = game_state["street"]
        pot = game_state["pot"]
        your_stack = game_state["your_stack"]
        amount_owed = game_state["amount_owed"]
        can_check = game_state.get("can_check", False)
        min_raise_to = game_state.get("min_raise_to", 0)
        current_bet = game_state.get("current_bet", 0)

        # Basic features
        to_call = amount_owed
        effective_stack = your_stack
        pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0

        hand_rank, equity, hand_type = get_hand_strength(your_cards, community)
        position = get_position(game_state)

        # ==================== PREFLOP ====================
        if street == "preflop":
            hand_str = "".join(sorted([c[0] + c[1] for c in your_cards], reverse=True))
            suited = your_cards[0][1] == your_cards[1][1]
            if suited and len(hand_str) == 4:
                hand_str = hand_str[:2] + "s"

            is_premium = hand_str in PREflop_RAISE_HANDS or (hand_str[:2] in ['AK', 'AQ', 'AJ'] and suited)

            if is_premium or equity > 0.65:
                if can_check:
                    return {"action": "check"}
                if min_raise_to > 0:
                    raise_size = max(min_raise_to, int(pot * 2.5))
                    raise_size = min(raise_size, your_stack + to_call)
                    return {"action": "raise", "amount": raise_size}
                return {"action": "call"}

            # Marginal hands - call in position, fold OOP
            if equity > 0.45 and position in ["late", "button"] and to_call < pot * 0.3:
                return {"action": "call"}

            return {"action": "fold"}

        # ==================== POSTFLOP ====================
        made_hand = hand_type in ["Straight Flush", "Quads", "Full House", "Flush", "Straight", "Three of a Kind",
                                  "Two Pair", "Pair"]
        draw_potential = equity > 0.35  # flush/straight draws etc.

        # Very strong hand -> value bet / raise
        if equity > 0.75 or made_hand and hand_type in ["Straight Flush", "Quads", "Full House", "Flush"]:
            if can_check:
                # Bet for value
                bet_size = max(min_raise_to, int(pot * 0.75))
                bet_size = min(bet_size, your_stack)
                if bet_size >= min_raise_to:
                    return {"action": "raise", "amount": bet_size}
                return {"action": "check"}
            else:
                # Facing bet - raise or call
                if to_call / pot < 0.4:  # good price
                    raise_size = max(min_raise_to, int((pot + to_call) * 2))
                    return {"action": "raise", "amount": min(raise_size, your_stack + to_call)}
                return {"action": "call"}

        # Medium strength + good equity
        if equity > 0.55:
            if can_check:
                # Semi-bluff or thin value
                if random.random() < 0.6 or draw_potential:
                    bet_size = max(min_raise_to or 0, int(pot * 0.5))
                    if bet_size > 0:
                        return {"action": "raise", "amount": min(bet_size, your_stack)}
                return {"action": "check"}
            else:
                if pot_odds < 0.25 or equity > pot_odds + 0.1:
                    return {"action": "call"}
                return {"action": "fold"}

        # Bluff / semi-bluff in position with draws
        if position in ["late", "button"] and draw_potential and random.random() < 0.45:
            if can_check:
                bet_size = max(min_raise_to or 0, int(pot * 0.6))
                if bet_size >= (min_raise_to or 0):
                    return {"action": "raise", "amount": min(bet_size, your_stack)}
            elif to_call < pot * 0.2:
                return {"action": "call"}

        # Default conservative
        if can_check:
            return {"action": "check"}
        if to_call == 0:
            return {"action": "check"}

        # Call only with decent equity and good pot odds
        if equity > pot_odds * 1.8:  # need roughly 1.8x the raw odds for implied
            return {"action": "call"}

        return {"action": "fold"}

    except Exception as e:
        # Safety net - better to fold than crash
        return {"action": "fold"}