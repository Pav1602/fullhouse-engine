import eval7
import random

def _rank_to_strength(rank):
    """Convert eval7 rank (1=best, 7462=worst) to a 0-1 strength."""
    return 1.0 - (rank - 1) / 7461.0

def preflop_strength(hole):
    """Strength based purely on hole cards."""
    cards = [eval7.Card(c) for c in hole]
    rank = eval7.evaluate(cards)
    return _rank_to_strength(rank)

def hand_strength(hole, community):
    """Best 5-card rank from hole + community."""
    cards = [eval7.Card(c) for c in hole + community]
    rank = eval7.evaluate(cards)
    return _rank_to_strength(rank)

def board_texture(community):
    """
    Return a 0-1 score of how scary the board is (good for bluffing).
    Factors: flush draw potential, straight potential, paired board, high cards.
    """
    if not community:
        return 0.0
    suits = {}
    ranks = []
    for c in community:
        card = eval7.Card(c)
        suit = card.suit
        rank = card.rank  # 2-14
        suits[suit] = suits.get(suit, 0) + 1
        ranks.append(rank)

    # Flush draw
    max_suit = max(suits.values())
    flush_score = 1.0 if max_suit >= 3 else 0.5 if max_suit == 2 else 0.0

    # Straight potential: look for 3 cards within a 5-rank window
    unique_ranks = sorted(set(ranks))
    straight_score = 0.0
    for i in range(len(unique_ranks) - 2):
        if unique_ranks[i+2] - unique_ranks[i] <= 4:
            straight_score = 1.0
            break
    # If not found, check for 2-card gutshot (loose)
    if straight_score == 0.0 and len(unique_ranks) >= 2:
        for i in range(len(unique_ranks)-1):
            if 1 <= unique_ranks[i+1] - unique_ranks[i] <= 2:
                straight_score = 0.3
                break

    # Paired board
    paired = len(ranks) != len(set(ranks))
    paired_score = 1.0 if paired else 0.0

    # High cards (Q, K, A)
    high_count = sum(1 for r in ranks if r >= 12)
    high_score = min(1.0, high_count / 3.0)

    # Weighted mix – tune as needed
    score = 0.3 * flush_score + 0.3 * straight_score + 0.2 * paired_score + 0.2 * high_score
    return min(1.0, score)


def decide(game_state: dict) -> dict:
    hole = game_state["your_cards"]
    community = game_state["community_cards"]
    street = game_state["street"]
    pot = game_state["pot"]
    stack = game_state["your_stack"]
    amount_owed = game_state["amount_owed"]
    can_check = game_state["can_check"]
    min_raise_to = game_state.get("min_raise_to", 0)

    # Hand strength
    if street == "preflop":
        strength = preflop_strength(hole)
    else:
        strength = hand_strength(hole, community)

    board_scare = board_texture(community) if street != "preflop" else 0.0
    facing_bet = amount_owed > 0
    r = random.random()

    # ---------- preflop ----------
    if street == "preflop":
        if can_check:
            # BB with no raise – free play
            if strength > 0.7:
                return _raise_action(min_raise_to, stack, pot, multiplier=2.0)
            elif strength > 0.4:
                if r < 0.5:
                    return _raise_action(min_raise_to, stack, pot, multiplier=2.0)
                return {"action": "check"}
            else:
                # weak, bluff sometimes
                if r < 0.3:
                    return _raise_action(min_raise_to, stack, pot, multiplier=2.0)
                return {"action": "check"}
        else:
            # Facing a bet / raise
            if strength > 0.8:   # premium
                return _raise_action(min_raise_to, stack, pot, multiplier=2.5)
            elif strength > 0.6:
                if r < 0.7:      # often 3-bet
                    return _raise_action(min_raise_to, stack, pot, multiplier=2.0)
                return _call_or_check(amount_owed, can_check)
            elif strength > 0.3:
                if r < 0.4:      # bluff raise
                    return _raise_action(min_raise_to, stack, pot, multiplier=2.5)
                elif amount_owed <= stack * 0.1:
                    return _call_or_check(amount_owed, can_check)
                else:
                    return {"action": "fold"}
            else:  # trash
                if r < 0.2:      # wild bluff
                    return _raise_action(min_raise_to, stack, pot, multiplier=2.5)
                return _call_or_check(amount_owed, can_check) if amount_owed == 0 else {"action": "fold"}

    # ---------- postflop ----------
    if not facing_bet:
        # Checked to us – we can bet or check
        if strength > 0.75:
            return _bet_action(pot, stack, fraction=0.75)
        elif strength > 0.5:
            bet_prob = 0.6 + 0.2 * board_scare
            if r < bet_prob:
                return _bet_action(pot, stack, fraction=0.66)
            return {"action": "check"}
        else:
            # Bluff
            bluff_prob = 0.5 * board_scare + 0.2
            if r < bluff_prob:
                return _bet_action(pot, stack, fraction=0.8)
            return {"action": "check"}
    else:
        # Facing a bet
        pot_odds = amount_owed / (pot + amount_owed) if (pot + amount_owed) > 0 else 0
        equity = strength  # proxy for actual equity

        if equity > 0.85:
            return _raise_action(min_raise_to, stack, pot, base=amount_owed, multiplier=2.5)
        elif equity > 0.6:
            if pot_odds < equity * 0.8:
                return _call_or_check(amount_owed, can_check)
            elif r < 0.3:
                return _raise_action(min_raise_to, stack, pot, base=amount_owed, multiplier=2.5)
            return _call_or_check(amount_owed, can_check)
        elif equity > 0.3:
            bluff_chance = board_scare * 0.5 + 0.1
            if r < bluff_chance and amount_owed < pot * 0.5:
                return _raise_action(min_raise_to, stack, pot, base=amount_owed, multiplier=2.5)
            elif pot_odds < equity:
                return _call_or_check(amount_owed, can_check)
            else:
                return {"action": "fold"}
        else:
            if r < 0.15:
                return _raise_action(min_raise_to, stack, pot, base=amount_owed, multiplier=2.5)
            return {"action": "fold"}

    # Fallback (should never be reached)
    if can_check:
        return {"action": "check"}
    elif amount_owed == 0:
        return {"action": "check"}
    return {"action": "fold"}


# ---------- helper functions ----------

def _raise_action(min_raise_to, stack, pot, base=0, multiplier=2.0):
    """
    Build a raise (or all-in) action.
    base: current bet to match (if any), 0 if opening.
    """
    desired = max(min_raise_to, base + int(pot * multiplier))
    if desired >= stack:
        return {"action": "all_in"}
    if min_raise_to > stack:
        # can't raise, fallback to call/all-in (caller should handle)
        return {"action": "call"} if stack >= min_raise_to else {"action": "fold"}
    return {"action": "raise", "amount": int(desired)}

def _bet_action(pot, stack, fraction=0.75):
    """Open bet as a raise."""
    amount = max(1, int(pot * fraction))
    if amount >= stack:
        return {"action": "all_in"}
    return {"action": "raise", "amount": amount}

def _call_or_check(amount_owed, can_check):
    if amount_owed == 0 and can_check:
        return {"action": "check"}
    if amount_owed == 0:
        return {"action": "check"}   # shouldn't happen, but safe
    return {"action": "call"}