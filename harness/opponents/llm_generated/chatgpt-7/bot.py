# bot.py
# Exploitative NLHE bot for weak-player pools in Fullhouse Engine
# Style: punish limpers, isolate callers, c-bet often, overfold to strength,
# value-bet thinly, bluff less on later streets.
#
# Uses eval7 if available, otherwise falls back to simple heuristics.

import random

try:
    import eval7
    HAS_EVAL7 = True
except:
    HAS_EVAL7 = False


# ----------------------------
# Helpers
# ----------------------------

RANKS = "23456789TJQKA"

def rank_value(card):
    return RANKS.index(card[0]) + 2

def suit(card):
    return card[1]

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def choose_raise(min_raise_to, pot, your_stack, factor=0.75):
    amt = max(min_raise_to, int(pot * factor))
    return min(amt, your_stack)

def pair(cards):
    return cards[0][0] == cards[1][0]

def suited(cards):
    return cards[0][1] == cards[1][1]

def connected(cards):
    return abs(rank_value(cards[0]) - rank_value(cards[1])) == 1

def broadway(card):
    return rank_value(card) >= 10

def hand_strength_preflop(cards):
    r1 = rank_value(cards[0])
    r2 = rank_value(cards[1])
    hi = max(r1, r2)
    lo = min(r1, r2)

    # premiums
    if pair(cards):
        if hi >= 11: return 0.95   # JJ+
        if hi >= 8: return 0.85    # 88-TT
        if hi >= 5: return 0.72
        return 0.60

    if hi == 14 and lo >= 10:
        return 0.88               # AK AQ AJ AT

    if hi >= 13 and lo >= 10:
        return 0.80               # KQ KJ KT

    if suited(cards) and connected(cards) and hi >= 10:
        return 0.75

    if suited(cards) and hi >= 12:
        return 0.70

    if connected(cards) and hi >= 9:
        return 0.62

    if suited(cards):
        return 0.55

    return 0.35


def monte_carlo_strength(hole, board, iters=120):
    if not HAS_EVAL7:
        return 0.5

    deck = eval7.Deck()
    used = [eval7.Card(c) for c in hole + board]

    for c in used:
        deck.cards.remove(c)

    hero = [eval7.Card(c) for c in hole]
    board_cards = [eval7.Card(c) for c in board]

    wins = 0
    ties = 0

    need = 5 - len(board_cards)

    for _ in range(iters):
        deck.shuffle()
        opp = deck.cards[:2]
        runout = deck.cards[2:2+need]

        full_board = board_cards + runout

        hero_val = eval7.evaluate(hero + full_board)
        opp_val = eval7.evaluate(list(opp) + full_board)

        if hero_val > opp_val:
            wins += 1
        elif hero_val == opp_val:
            ties += 1

    return (wins + ties * 0.5) / iters


def detect_weak_pool(players):
    """
    If many stacks shrinking unevenly and many active players,
    assume loose/passive field.
    """
    alive = sum(1 for p in players if p.get("stack", 0) > 0)
    return alive >= 4


def count_callers(action_log):
    calls = 0
    for a in action_log[-20:]:
        if isinstance(a, dict):
            if a.get("action") == "call":
                calls += 1
    return calls


# ----------------------------
# Main Decision
# ----------------------------

def decide(game_state: dict) -> dict:
    cards = game_state["your_cards"]
    board = game_state["community_cards"]
    street = game_state["street"]
    pot = game_state["pot"]
    stack = game_state["your_stack"]
    owed = game_state["amount_owed"]
    can_check = game_state["can_check"]
    min_raise_to = game_state["min_raise_to"]
    players = game_state["players"]
    action_log = game_state["action_log"]

    weak_pool = detect_weak_pool(players)
    callers = count_callers(action_log)

    # ---------------- PRE-FLOP ----------------
    if street == "preflop":
        s = hand_strength_preflop(cards)

        # Exploit weak players: raise stronger/wider when limped to us
        if owed == 0:
            if s > 0.58:
                amt = choose_raise(min_raise_to, pot + 1, stack, 1.0)
                return {"action": "raise", "amount": amt}
            return {"action": "check"}

        # Facing raise: weak fields overbluff less -> tighter continue
        pot_odds = owed / max(1, pot + owed)

        if s > 0.82:
            if random.random() < 0.55:
                amt = choose_raise(min_raise_to, pot, stack, 1.25)
                return {"action": "raise", "amount": amt}
            return {"action": "call"}

        if s > 0.60 and pot_odds < 0.28:
            return {"action": "call"}

        if s > 0.48 and weak_pool and callers >= 1 and pot_odds < 0.18:
            return {"action": "call"}

        return {"action": "fold"}

    # ---------------- POSTFLOP ----------------
    strength = monte_carlo_strength(cards, board)

    # Free action
    if can_check:
        # c-bet often into weak players heads-up / small field
        if strength > 0.55:
            if random.random() < 0.65:
                amt = choose_raise(min_raise_to, pot, stack, 0.65)
                return {"action": "raise", "amount": amt}
        return {"action": "check"}

    # Facing bet
    pot_odds = owed / max(1, pot + owed)

    # Nuts / strong made hand
    if strength > 0.82:
        if random.random() < 0.65:
            amt = choose_raise(min_raise_to, pot, stack, 0.9)
            return {"action": "raise", "amount": amt}
        return {"action": "call"}

    # Medium strength bluff-catchers
    if strength > 0.62 and pot_odds < 0.32:
        return {"action": "call"}

    # Draws / decent equity
    if strength > 0.48 and pot_odds < 0.20:
        return {"action": "call"}

    # Exploit weak passive players: fold to big aggression
    if owed > pot * 0.75:
        return {"action": "fold"}

    return {"action": "fold"}