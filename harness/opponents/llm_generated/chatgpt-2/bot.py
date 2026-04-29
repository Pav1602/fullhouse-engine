# bot.py
# Fullhouse Engine entrypoint
# Approximate GTO-style NLHE tournament bot for 6-max.
# Uses mixed strategies, position, pot odds, board texture, MDF-ish defense,
# and Monte Carlo equity estimation with eval7.
#
# Designed for Fullhouse Engine constraints:
# - single file
# - fast enough for 2s limit
# - no I/O
#
# Requires: eval7

import random
import math

try:
    import eval7
except:
    eval7 = None


# -----------------------------
# Utility helpers
# -----------------------------

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def card_rank(c):
    return RANKS.index(c[0])


def is_pair(cards):
    return cards[0][0] == cards[1][0]


def is_suited(cards):
    return cards[0][1] == cards[1][1]


def gap(cards):
    r1 = card_rank(cards[0])
    r2 = card_rank(cards[1])
    return abs(r1 - r2)


def hand_strength_preflop(cards):
    """
    Lightweight preflop score.
    """
    r1 = card_rank(cards[0])
    r2 = card_rank(cards[1])
    hi = max(r1, r2)
    lo = min(r1, r2)

    score = hi * 2 + lo

    if is_pair(cards):
        score += 18 + hi

    if is_suited(cards):
        score += 3

    g = gap(cards)
    if g == 1:
        score += 2
    elif g == 2:
        score += 1
    elif g >= 4:
        score -= 2

    # broadways
    if hi >= 8 and lo >= 8:
        score += 3

    return score


def position_index(players, me_stack):
    """
    Rough positional estimate:
    later index = later position.
    """
    active = [p for p in players if p.get("stack", 0) > 0]
    n = len(active)
    if n <= 2:
        return 1.0
    return min(1.0, max(0.0, (n - 1) / 5))


def pot_odds_to_call(amount_owed, pot):
    if amount_owed <= 0:
        return 0
    return amount_owed / (pot + amount_owed)


# -----------------------------
# Postflop equity estimation
# -----------------------------

def estimate_equity(hero_cards, board_cards, opp_count=1, iters=120):
    """
    Monte Carlo equity vs random range.
    """
    if eval7 is None:
        return 0.5

    try:
        hero = [eval7.Card(c) for c in hero_cards]
        board = [eval7.Card(c) for c in board_cards]

        used = set(hero + board)
        deck = eval7.Deck()
        deck.cards = [c for c in deck.cards if c not in used]

        wins = 0
        ties = 0

        for _ in range(iters):
            random.shuffle(deck.cards)

            draw_index = 0

            opp_hands = []
            for _ in range(opp_count):
                opp_hands.append(
                    [deck.cards[draw_index], deck.cards[draw_index + 1]]
                )
                draw_index += 2

            remain = 5 - len(board)
            runout = board + deck.cards[draw_index:draw_index + remain]

            hero_val = eval7.evaluate(hero + runout)

            best = hero_val
            result = 1

            for opp in opp_hands:
                v = eval7.evaluate(opp + runout)
                if v > best:
                    result = 0
                    best = v
                elif v == best and result == 1:
                    result = 0.5

            if result == 1:
                wins += 1
            elif result == 0.5:
                ties += 1

        return (wins + ties * 0.5) / iters

    except:
        return 0.5


# -----------------------------
# Bet sizing
# -----------------------------

def choose_raise_size(gs, factor):
    pot = gs["pot"]
    min_raise = gs.get("min_raise_to", 0)
    stack = gs["your_stack"]

    target = int(max(min_raise, pot * factor))
    target = min(target, stack)
    return target


def maybe_raise(freq):
    return random.random() < freq


# -----------------------------
# Core strategy
# -----------------------------

def preflop_decision(gs):
    cards = gs["your_cards"]
    score = hand_strength_preflop(cards)

    owed = gs["amount_owed"]
    can_check = gs["can_check"]
    pot = gs["pot"]

    pos = position_index(gs["players"], gs["your_stack"])

    # stronger in late position
    score += pos * 4

    # Open when checked to
    if can_check:
        if score >= 22 and maybe_raise(0.75):
            amt = choose_raise_size(gs, 2.5)
            return {"action": "raise", "amount": amt}
        return {"action": "check"}

    # Facing bet
    odds = pot_odds_to_call(owed, pot)

    # Premium hands
    if score >= 30:
        if maybe_raise(0.65):
            amt = choose_raise_size(gs, 3.0)
            return {"action": "raise", "amount": amt}
        return {"action": "call"}

    # Strong hands
    if score >= 24:
        if odds <= 0.35:
            if maybe_raise(0.25):
                amt = choose_raise_size(gs, 2.8)
                return {"action": "raise", "amount": amt}
            return {"action": "call"}

    # Medium defend range
    if score >= 18:
        if odds <= 0.22 + pos * 0.08:
            return {"action": "call"}

    # MDF light defense vs tiny bets
    if odds <= 0.12 and maybe_raise(0.05):
        return {"action": "call"}

    return {"action": "fold"}


def postflop_decision(gs):
    board = gs["community_cards"]
    hero = gs["your_cards"]

    street = gs["street"]
    owed = gs["amount_owed"]
    pot = gs["pot"]
    can_check = gs["can_check"]

    # fewer sims later streets = enough info
    sims = {
        "flop": 140,
        "turn": 110,
        "river": 80
    }.get(street, 100)

    eq = estimate_equity(hero, board, opp_count=1, iters=sims)
    odds = pot_odds_to_call(owed, pot)

    # Aggression thresholds by street
    thin_value = {"flop": 0.62, "turn": 0.60, "river": 0.56}[street]
    strong_value = {"flop": 0.75, "turn": 0.72, "river": 0.68}[street]
    bluff_zone = {"flop": 0.28, "turn": 0.22, "river": 0.15}[street]

    # If checked to us
    if can_check:
        if eq >= strong_value:
            amt = choose_raise_size(gs, 0.9)
            return {"action": "raise", "amount": amt}

        if eq >= thin_value and maybe_raise(0.65):
            amt = choose_raise_size(gs, 0.55)
            return {"action": "raise", "amount": amt}

        # balanced bluff frequency
        if eq <= bluff_zone and maybe_raise(0.22):
            amt = choose_raise_size(gs, 0.6)
            return {"action": "raise", "amount": amt}

        return {"action": "check"}

    # Facing bet

    # Raise strong hands
    if eq >= strong_value:
        if maybe_raise(0.75):
            amt = choose_raise_size(gs, 2.0)
            return {"action": "raise", "amount": amt}
        return {"action": "call"}

    # Call profitable hands
    if eq >= odds + 0.05:
        return {"action": "call"}

    # Bluff jam sometimes vs weak blockers on river (rare)
    if street == "river" and eq < 0.20 and owed < pot * 0.4 and maybe_raise(0.08):
        amt = choose_raise_size(gs, 2.2)
        return {"action": "raise", "amount": amt}

    return {"action": "fold"}


# -----------------------------
# Entry point
# -----------------------------

def decide(game_state: dict) -> dict:
    try:
        street = game_state["street"]

        # short stack push/fold adjustments
        if game_state["your_stack"] <= max(10, game_state["pot"]):
            cards = game_state["your_cards"]
            score = hand_strength_preflop(cards)
            if street == "preflop":
                if score >= 22:
                    return {"action": "all_in"}
                elif game_state["can_check"]:
                    return {"action": "check"}
                elif score >= 18:
                    return {"action": "call"}
                return {"action": "fold"}

        if street == "preflop":
            return preflop_decision(game_state)

        return postflop_decision(game_state)

    except:
        # fail-safe
        if game_state.get("can_check", False):
            return {"action": "check"}
        return {"action": "fold"}