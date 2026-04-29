import eval7
import random

# Pre-compute basic tight-aggressive (TAG) preflop tiers to bypass expensive MC sims
PREMIUM_PAIRS = [{"A", "A"}, {"K", "K"}, {"Q", "Q"}, {"J", "J"}, {"T", "T"}]
STRONG_BROADWAY = [{"A", "K"}, {"A", "Q"}, {"K", "Q"}]


def is_strong_preflop(ranks):
    rank_set = set(ranks)
    # Check for pocket pairs
    if len(ranks) == 2 and ranks[0] == ranks[1]:
        return any(rank_set == pair for pair in PREMIUM_PAIRS)
    # Check for strong unmatched
    return any(rank_set == broadway for broadway in STRONG_BROADWAY)


def mc_equity(hole_cards, board_cards, iters=3000):
    """
    Monte Carlo simulation against a random opponent hand.
    With a 2s timeout and 0.5 CPU, 3000 Python iterations calling eval7's C-backend is safe.
    """
    deck = eval7.Deck()
    hole = [eval7.Card(c) for c in hole_cards]
    board = [eval7.Card(c) for c in board_cards]

    # Remove known cards from the deck
    for c in hole + board:
        deck.cards.remove(c)

    wins = 0
    ties = 0

    # Pre-calculate to avoid loop overhead
    board_len = len(board)
    cards_to_draw = 5 - board_len
    total_draw = cards_to_draw + 2  # board completion + villain's 2 hole cards

    for _ in range(iters):
        deck.shuffle()
        draw = deck.peek(total_draw)

        sim_board = board + draw[:cards_to_draw]
        villain_hole = draw[cards_to_draw:]

        my_score = eval7.evaluate(hole + sim_board)
        villain_score = eval7.evaluate(villain_hole + sim_board)

        if my_score > villain_score:
            wins += 1
        elif my_score == villain_score:
            ties += 1

    return (wins + (ties / 2.0)) / iters


def decide(game_state: dict) -> dict:
    street = game_state.get("street")
    hole_cards = game_state.get("your_cards", [])
    board = game_state.get("community_cards", [])
    pot = game_state.get("pot", 0)
    owed = game_state.get("amount_owed", 0)
    can_check = game_state.get("can_check", False)
    min_raise = game_state.get("min_raise_to", 0)
    stack = game_state.get("your_stack", 0)

    # 1. Preflop Logic (Static mapping)
    if street == "preflop":
        ranks = [c[0] for c in hole_cards]
        if is_strong_preflop(ranks):
            # 3-bet or open raise
            if owed > 0 and stack >= min_raise:
                return {"action": "raise", "amount": min_raise * 2}
            return {"action": "call"} if owed > 0 else {"action": "raise", "amount": min_raise}

        if can_check:
            return {"action": "check"}

        # Speculative call if pot odds are incredibly cheap (< 10% of pot)
        if owed > 0 and (owed / (pot + owed)) < 0.10:
            return {"action": "call"}

        return {"action": "fold"}

    # 2. Postflop Logic (Monte Carlo EV)
    # Calculate pure pot odds. e.g., calling 100 to win a 400 pot = 0.20 odds.
    pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 0

    # Calculate pure hand equity against a random holding
    equity = mc_equity(hole_cards, board)

    # Add a risk premium margin to avoid calling marginally losing bets due to MC variance
    margin = 0.08
    required_equity = pot_odds + margin

    # 3. Action Execution
    if equity > 0.80:
        # Premium hand: Value bet / raise territory
        raise_amt = max(min_raise, int(pot * 0.60))
        if raise_amt < stack:
            return {"action": "raise", "amount": raise_amt}
        return {"action": "all_in"}

    elif equity > required_equity:
        if owed == 0 and stack >= min_raise:
            # Probe bet if checked to us
            return {"action": "raise", "amount": min_raise}
        return {"action": "call"}

    else:
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}