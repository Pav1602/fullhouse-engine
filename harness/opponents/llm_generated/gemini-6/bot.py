import eval7
import random


def get_preflop_action(hole_cards, current_bet, min_raise_to, pot, can_check, amount_owed):
    """
    Evaluates preflop hands using a tight-aggressive (TAG) tier system.
    """
    ranks = "23456789TJQKA"

    # Parse cards
    r1, s1 = hole_cards[0][0], hole_cards[0][1]
    r2, s2 = hole_cards[1][0], hole_cards[1][1]

    idx1, idx2 = ranks.index(r1), ranks.index(r2)
    if idx1 < idx2:
        idx1, idx2 = idx2, idx1
        r1, r2 = r2, r1

    is_suited = (s1 == s2)
    is_pair = (r1 == r2)

    # Calculate pot odds for calling
    pot_odds = amount_owed / (pot + amount_owed) if (pot + amount_owed) > 0 else 1.0

    # Tier 1: Premium pairs and AKs - Always raise/shove
    if is_pair and idx1 >= ranks.index('J'):
        return {"action": "raise", "amount": min_raise_to * 2}
    if is_suited and r1 == 'A' and r2 == 'K':
        return {"action": "raise", "amount": min_raise_to * 2}

    # Tier 2: Mid pairs, strong broadways - Raise or call
    if is_pair and idx1 >= ranks.index('7'):
        if current_bet == 0: return {"action": "raise", "amount": min_raise_to}
        if pot_odds < 0.4: return {"action": "call"}
    if is_suited and idx1 >= ranks.index('A') and idx2 >= ranks.index('J'):
        if current_bet == 0: return {"action": "raise", "amount": min_raise_to}
        if pot_odds < 0.35: return {"action": "call"}
    if not is_suited and r1 == 'A' and r2 == 'K':
        if current_bet == 0: return {"action": "raise", "amount": min_raise_to}
        if pot_odds < 0.35: return {"action": "call"}

    # Tier 3: Suited connectors, weak pairs - Call if cheap
    if is_pair:
        if pot_odds < 0.15: return {"action": "call"}
    if is_suited and (idx1 - idx2 == 1) and idx1 >= ranks.index('7'):
        if pot_odds < 0.2: return {"action": "call"}

    # Default logic
    if can_check:
        return {"action": "check"}
    return {"action": "fold"}


def calculate_equity(hole_cards, community_cards, iterations=1000):
    """
    Runs a fast Monte Carlo simulation to approximate hand equity.
    Iterations tuned to stay well under the 2-second timeout per action limit.
    """
    deck = eval7.Deck()
    hole = [eval7.Card(c) for c in hole_cards]
    board = [eval7.Card(c) for c in community_cards]

    # Remove known cards from the deck
    for card in hole + board:
        deck.cards.remove(card)

    wins = 0
    ties = 0

    for _ in range(iterations):
        deck.shuffle()
        cards_to_draw = 5 - len(board)

        # Draw for board completion and opponent's hand
        draw = deck.peek(cards_to_draw + 2)
        opp_hole = draw[:2]
        sim_board = board + draw[2:]

        my_val = eval7.evaluate(hole + sim_board)
        opp_val = eval7.evaluate(opp_hole + sim_board)

        if my_val > opp_val:
            wins += 1
        elif my_val == opp_val:
            ties += 1

    return (wins + (ties / 2.0)) / iterations


def decide(game_state: dict) -> dict:
    """
    Main decision engine. Failsafe wrapper prevents unhandled exceptions
    from causing an auto-fold, keeping the bot alive in the tournament.
    """
    try:
        cards = game_state.get("your_cards", [])
        board = game_state.get("community_cards", [])
        street = game_state.get("street", "preflop")
        can_check = game_state.get("can_check", False)
        min_raise = game_state.get("min_raise_to", 0)
        amount_owed = game_state.get("amount_owed", 0)
        pot = game_state.get("pot", 0)
        stack = game_state.get("your_stack", 0)
        current_bet = game_state.get("current_bet", 0)

        # Preflop Strategy
        if street == "preflop":
            return get_preflop_action(cards, current_bet, min_raise, pot, can_check, amount_owed)

        # Postflop Strategy (Flop, Turn, River)
        equity = calculate_equity(cards, board, iterations=800)

        # Calculate required pot odds
        pot_odds = amount_owed / (pot + amount_owed) if (pot + amount_owed) > 0 else 0

        # Action mapping based on raw equity vs pot odds
        if equity > 0.80:
            # Value bet / Shove
            if stack <= min_raise:
                return {"action": "all_in"}
            target_raise = min_raise + int(pot * 0.75)
            return {"action": "raise", "amount": min(stack, target_raise)}

        elif equity > 0.65:
            # Strong hand, build pot
            return {"action": "raise", "amount": min_raise}

        elif equity > pot_odds + 0.05:  # 5% safety margin on calls
            # Profitable call
            return {"action": "call"}

        else:
            # Fold weak hands, but take free checks
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

    except Exception as e:
        # Failsafe: if anything breaks, check/fold rather than crash the thread
        if game_state.get("can_check", False):
            return {"action": "check"}
        return {"action": "fold"}