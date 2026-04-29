import eval7
import random


def get_preflop_action(game_state):
    cards = game_state["your_cards"]
    pot = game_state["pot"]
    owed = game_state["amount_owed"]
    current_bet = game_state["current_bet"]
    min_raise = game_state.get("min_raise_to", current_bet * 2 if current_bet > 0 else 20)
    can_check = game_state["can_check"]
    my_stack = game_state["your_stack"]

    # Standardize rank ordering
    ranks = "23456789TJQKA"
    r1, s1 = cards[0][0], cards[0][1]
    r2, s2 = cards[1][0], cards[1][1]

    idx1, idx2 = ranks.index(r1), ranks.index(r2)
    if idx1 < idx2:
        r1, r2 = r2, r1
        idx1, idx2 = idx2, idx1

    is_suited = (s1 == s2)
    is_pair = (r1 == r2)

    # Tier 1: Premium | Tier 2: Strong | Tier 3: Playable | Tier 4: Marginal | Tier 5: Trash
    tier = 5
    if is_pair:
        tier = 1 if r1 in "AA KK QQ JJ TT" else 2 if r1 in "99 88 77" else 3
    elif is_suited:
        if r1 == 'A' and r2 in "K Q J":
            tier = 1
        elif r1 == 'K' and r2 in "Q J":
            tier = 2
        elif r1 == 'A' or (idx1 - idx2 <= 2 and idx1 >= 8):
            tier = 3
        elif idx1 - idx2 <= 1:
            tier = 4
    else:
        if r1 == 'A' and r2 in "K Q":
            tier = 1
        elif r1 == 'A' and r2 == 'J':
            tier = 2
        elif r1 == 'K' and r2 in "Q J":
            tier = 3
        elif r1 == 'A':
            tier = 4

    pot_odds = owed / (pot + owed + 1e-6)

    # Pseudo-GTO Preflop Action Matrix
    if tier == 1:
        if my_stack > min_raise and current_bet < pot * 1.5:
            return {"action": "raise", "amount": max(min_raise, int(pot))}
        return {"action": "all_in"} if owed >= my_stack else {"action": "call"}
    elif tier == 2:
        if owed <= pot * 0.5 and my_stack > min_raise:
            return {"action": "raise", "amount": max(min_raise, int(pot * 0.75))}
        elif pot_odds < 0.4:
            return {"action": "call"}
    elif tier == 3:
        if owed == 0 and my_stack > min_raise:
            return {"action": "raise", "amount": max(min_raise, int(pot * 0.5))}
        elif pot_odds < 0.3:
            return {"action": "call"}
    elif tier == 4:
        if pot_odds < 0.15:
            return {"action": "call"}

    return {"action": "check"} if can_check else {"action": "fold"}


def monte_carlo_equity(hole_str, board_str, iters=800):
    deck = [eval7.Card(r + s) for r in "23456789TJQKA" for s in "cdhs"]
    known_strs = set(hole_str + board_str)

    # Purge visible cards from the simulation deck
    deck = [c for c in deck if str(c) not in known_strs]

    hole_cards = [eval7.Card(c) for c in hole_str]
    board_cards = [eval7.Card(c) for c in board_str]

    wins, ties = 0, 0
    cards_needed = 5 - len(board_cards)

    for _ in range(iters):
        # Use random.sample (O(k)) instead of random.shuffle (O(N)) to dodge 2s CPU timeout limits
        draw = random.sample(deck, cards_needed + 2)
        sim_board = board_cards + draw[:cards_needed]
        opp_hole = draw[cards_needed:]

        # eval7 cleanly evaluates 7 cards (finding the best 5-card subset automatically)
        my_val = eval7.evaluate(hole_cards + sim_board)
        opp_val = eval7.evaluate(opp_hole + sim_board)

        if my_val > opp_val:
            wins += 1
        elif my_val == opp_val:
            ties += 1

    return (wins + ties / 2.0) / iters


def decide(game_state: dict) -> dict:
    street = game_state["street"]

    # Hand off to static tree for preflop
    if street == "preflop":
        return get_preflop_action(game_state)

    pot = game_state["pot"]
    owed = game_state["amount_owed"]
    my_stack = game_state["your_stack"]
    min_raise = game_state.get("min_raise_to", 0)
    can_check = game_state["can_check"]

    equity = monte_carlo_equity(game_state["your_cards"], game_state["community_cards"], iters=800)
    pot_odds = owed / (pot + owed + 1e-6)

    # Exploitative Range Penalty:
    # If the opponent is dropping a heavy bet (>30% of the pot), they aren't playing a 100% random range.
    # We penalize our raw equity by 5% mechanically to adjust for their perceived strength.
    range_penalty = 0.05 if owed > pot * 0.3 else 0.0
    effective_equity = equity - range_penalty

    if effective_equity > 0.75:
        if my_stack > min_raise:
            return {"action": "raise", "amount": max(min_raise, int(pot * 0.75 + owed))}
        return {"action": "all_in"}

    elif effective_equity > 0.55:
        if owed == 0 and my_stack > min_raise:
            return {"action": "raise", "amount": max(min_raise, int(pot * 0.5))}
        return {"action": "call"}

    elif effective_equity > pot_odds + 0.02:  # Safety margin
        return {"action": "call"}

    return {"action": "check"} if can_check else {"action": "fold"}