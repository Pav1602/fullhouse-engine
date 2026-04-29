# bot.py
# Fullhouse Engine tournament-style adaptive bot
# Focus: stack-depth adjustments, position, shove/fold zones, postflop pressure
# Uses only standard lib + optional eval7 if available

import random
import math

try:
    import eval7
except:
    eval7 = None


# ---------------------------
# Helpers
# ---------------------------

RANKS = "23456789TJQKA"
SUITS = "cdhs"

def card_rank(card):
    return RANKS.index(card[0])

def pair(cards):
    return cards[0][0] == cards[1][0]

def suited(cards):
    return cards[0][1] == cards[1][1]

def connected(cards):
    return abs(card_rank(cards[0]) - card_rank(cards[1])) == 1

def gap(cards):
    return abs(card_rank(cards[0]) - card_rank(cards[1]))

def high_card(cards):
    return max(card_rank(cards[0]), card_rank(cards[1]))

def low_card(cards):
    return min(card_rank(cards[0]), card_rank(cards[1]))

def effective_stack(gs):
    stacks = [p.get("stack", gs["your_stack"]) for p in gs.get("players", []) if p.get("active", True)]
    if not stacks:
        return gs["your_stack"]
    return min(gs["your_stack"], max(1, min(stacks)))

def bb_size(gs):
    # infer BB from min_raise_to if possible
    return max(20, gs.get("min_raise_to", 100) // 2)

def stack_bb(gs):
    return effective_stack(gs) / bb_size(gs)

def pot_odds(gs):
    owed = gs["amount_owed"]
    if owed <= 0:
        return 0
    return owed / (gs["pot"] + owed)

def in_position(gs):
    players = gs.get("players", [])
    me = None
    for i, p in enumerate(players):
        if p.get("is_you"):
            me = i
            break
    if me is None:
        return False
    active = [i for i,p in enumerate(players) if p.get("active", True)]
    return me == active[-1]

def street_index(street):
    return {"preflop":0,"flop":1,"turn":2,"river":3}.get(street,0)

def legal_raise(gs, amt):
    return max(gs["min_raise_to"], amt)

def rand_mix(p):
    return random.random() < p


# ---------------------------
# Hand Strength (Preflop)
# ---------------------------

def preflop_score(cards):
    r1 = card_rank(cards[0])
    r2 = card_rank(cards[1])
    hi = max(r1, r2)
    lo = min(r1, r2)

    score = 0

    if pair(cards):
        score += 45 + hi * 4

    score += hi * 3
    score += lo * 1.5

    if suited(cards):
        score += 6

    g = gap(cards)
    if g == 1:
        score += 5
    elif g == 2:
        score += 2
    elif g >= 4:
        score -= 4

    # Broadways
    if hi >= 8 and lo >= 8:
        score += 7

    return score


# ---------------------------
# Monte Carlo Approximation
# ---------------------------

def estimate_equity(cards, board, iters=120):
    if not eval7:
        return None

    hero = [eval7.Card(c) for c in cards]
    community = [eval7.Card(c) for c in board]

    deck = eval7.Deck()
    used = set(hero + community)
    deck.cards = [c for c in deck.cards if c not in used]

    wins = ties = 0

    need = 5 - len(community)

    for _ in range(iters):
        deck.shuffle()
        opp = deck.cards[:2]
        runout = deck.cards[2:2+need]

        hero_hand = hero + community + runout
        opp_hand = list(opp) + community + runout

        hv = eval7.evaluate(hero_hand)
        ov = eval7.evaluate(opp_hand)

        if hv > ov:
            wins += 1
        elif hv == ov:
            ties += 1

    return (wins + ties * 0.5) / iters


# ---------------------------
# Preflop Strategy by Stack Depth
# ---------------------------

def preflop_decide(gs):
    cards = gs["your_cards"]
    score = preflop_score(cards)
    bb = stack_bb(gs)
    owed = gs["amount_owed"]
    can_check = gs["can_check"]
    pos = in_position(gs)

    # SHORT STACK: <=12bb shove/fold
    if bb <= 12:
        jam_threshold = 62 if pos else 68
        if score >= jam_threshold:
            return {"action":"all_in"}
        if can_check:
            return {"action":"check"}
        if owed <= bb_size(gs) and score >= 50:
            return {"action":"call"}
        return {"action":"fold"}

    # MID STACK: 13-25bb raise/call/jam
    if bb <= 25:
        if score >= 72:
            if owed > 0 and rand_mix(0.35):
                return {"action":"all_in"}
            return {"action":"raise", "amount": legal_raise(gs, gs["min_raise_to"])}
        if score >= 56:
            if owed == 0:
                return {"action":"raise", "amount": legal_raise(gs, gs["min_raise_to"])}
            if pot_odds(gs) < 0.32:
                return {"action":"call"}
        if can_check:
            return {"action":"check"}
        return {"action":"fold"}

    # DEEP STACK: >25bb
    open_thresh = 44 if pos else 50
    raise_thresh = 58 if pos else 64

    if owed == 0:
        if score >= raise_thresh:
            mult = 2.2 if bb > 60 else 2.5
            raise_to = int(mult * bb_size(gs))
            return {"action":"raise", "amount": legal_raise(gs, raise_to)}
        if score >= open_thresh and rand_mix(0.45):
            raise_to = int(2.2 * bb_size(gs))
            return {"action":"raise", "amount": legal_raise(gs, raise_to)}
        return {"action":"check"}

    # facing raise
    if score >= 74:
        if rand_mix(0.45):
            r = int(gs["current_bet"] * 2.8)
            return {"action":"raise", "amount": legal_raise(gs, r)}
        return {"action":"call"}

    if score >= 58 and pot_odds(gs) < 0.28:
        return {"action":"call"}

    return {"action":"fold"}


# ---------------------------
# Postflop Strategy
# ---------------------------

def postflop_decide(gs):
    cards = gs["your_cards"]
    board = gs["community_cards"]
    owed = gs["amount_owed"]
    can_check = gs["can_check"]
    pot = gs["pot"]
    bb = stack_bb(gs)
    pos = in_position(gs)

    eq = estimate_equity(cards, board, 100)
    if eq is None:
        eq = 0.5

    # Strong hands / likely value
    if eq > 0.78:
        if owed == 0:
            bet = int(pot * 0.75)
            return {"action":"raise", "amount": legal_raise(gs, gs["current_bet"] + bet)}
        if rand_mix(0.45):
            return {"action":"all_in"}
        return {"action":"call"}

    # Medium strength
    if eq > 0.58:
        if owed == 0:
            if rand_mix(0.55):
                bet = int(pot * 0.45)
                return {"action":"raise", "amount": legal_raise(gs, gs["current_bet"] + bet)}
            return {"action":"check"}
        if pot_odds(gs) < eq:
            return {"action":"call"}
        return {"action":"fold"}

    # Draws / semibluffs
    if eq > 0.36:
        if owed == 0 and pos and rand_mix(0.35):
            bet = int(pot * 0.55)
            return {"action":"raise", "amount": legal_raise(gs, gs["current_bet"] + bet)}
        if pot_odds(gs) < eq - 0.05:
            return {"action":"call"}
        if can_check:
            return {"action":"check"}
        return {"action":"fold"}

    # Weak hands
    if can_check:
        if pos and rand_mix(0.18):
            bet = int(pot * 0.4)
            return {"action":"raise", "amount": legal_raise(gs, gs["current_bet"] + bet)}
        return {"action":"check"}

    return {"action":"fold"}


# ---------------------------
# Main Entry
# ---------------------------

def decide(game_state: dict) -> dict:
    try:
        if game_state["street"] == "preflop":
            return preflop_decide(game_state)
        return postflop_decide(game_state)
    except:
        # never crash in tournament
        if game_state.get("can_check", False):
            return {"action":"check"}
        return {"action":"fold"}