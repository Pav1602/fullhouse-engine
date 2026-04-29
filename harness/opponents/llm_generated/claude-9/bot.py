"""
Fullhouse Engine — 6-max NLHE Bot
Strategy: Position-aware preflop ranges + Monte Carlo equity postflop
Author: bot.py template for fullhouse-engine competition
"""

import eval7
import random

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

RANK_MAP = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
}

# 6-max position order clockwise from BTN: BTN=0, SB=1, BB=2, UTG=3, HJ=4, CO=5
POSITIONS_6MAX = {0: 'BTN', 1: 'SB', 2: 'BB', 3: 'UTG', 4: 'HJ', 5: 'CO'}

# Position equity bonus (in-position = can realise equity better)
POS_BONUS = {
    'BTN': +0.05,
    'CO':  +0.03,
    'HJ':  +0.01,
    'UTG': -0.02,
    'SB':  -0.03,
    'BB':  -0.01,
}

# ──────────────────────────────────────────────────────────────────────────────
# POSITION DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def detect_position(players: list) -> str:
    """
    Infer our seat position from the players list.
    Tries several field-name conventions; falls back to 'CO' if ambiguous.
    """
    my_seat = None
    dealer_seat = None
    n = len(players)

    for i, p in enumerate(players):
        # Identify our seat
        if p.get('is_me') or p.get('you') or p.get('name') in ('you', 'me', 'bot'):
            my_seat = i
        # Identify dealer/button
        if p.get('is_dealer') or p.get('dealer') or p.get('button') or p.get('is_button'):
            dealer_seat = i
        # Some engines embed position directly
        if (p.get('is_me') or p.get('you')) and p.get('position'):
            return p['position']

    if my_seat is not None and dealer_seat is not None:
        rel = (my_seat - dealer_seat) % n
        return POSITIONS_6MAX.get(rel, 'CO')

    return 'CO'  # Safe default: treat unknown as late position


def count_active_opponents(players: list) -> int:
    """Count opponents still in the hand (not folded, not us)."""
    inactive = {'folded', 'out', 'eliminated', 'bust'}
    n = sum(
        1 for p in players
        if p.get('status', '').lower() not in inactive
        and not (p.get('is_me') or p.get('you'))
    )
    return max(1, n)


# ──────────────────────────────────────────────────────────────────────────────
# PREFLOP HAND STRENGTH
# ──────────────────────────────────────────────────────────────────────────────

def hand_score(c1: str, c2: str) -> float:
    """
    Score two hole cards 0-100. Higher = stronger.
    Built from 6-max GTO open-raise charts; calibrated against Chen formula.
    """
    r1, s1 = c1[:-1], c1[-1]
    r2, s2 = c2[:-1], c2[-1]
    v1, v2 = RANK_MAP[r1], RANK_MAP[r2]

    is_pair  = (r1 == r2)
    is_suited = (s1 == s2)
    hi, lo = max(v1, v2), min(v1, v2)
    gap = hi - lo

    if is_pair:
        # AA=92, KK=89, QQ=86 … 22=56
        score = 50 + hi * 3.0
    else:
        # Base: weighted hi-lo value
        score = hi * 2.5 + lo * 0.8
        if is_suited:
            score += 4.0
        # Connectivity bonus/penalty
        if gap == 1:
            score += 3.0
        elif gap == 2:
            score += 1.5
        elif gap >= 4:
            score -= (gap - 3) * 2.0
        # Low card penalty — rags lose post-flop
        if lo < 7:
            score -= (7 - lo) * 1.5

    return score


def preflop_threshold(position: str, n_opponents: int) -> float:
    """
    Minimum hand score to voluntarily put chips in preflop.
    Wider ranges in late position, tighter vs more opponents.
    """
    base = {
        'BTN': 52.0,  # Steal most often — positional advantage post-flop
        'CO':  55.0,
        'HJ':  59.0,
        'UTG': 63.0,  # UTG+0 in 6-max still opens ~18-20% of hands
        'SB':  54.0,  # Can complete cheap; IP stolen from BB
        'BB':  48.0,  # Closing action; pot odds already baked in
    }.get(position, 57.0)

    # Tighten with more players still to act
    return base + max(0, (n_opponents - 2) * 1.5)


# ──────────────────────────────────────────────────────────────────────────────
# MONTE CARLO EQUITY ESTIMATION
# ──────────────────────────────────────────────────────────────────────────────

_ALL_CARDS = [r + s for r in '23456789TJQKA' for s in 'shdc']


def estimate_equity(hole_cards: list, community: list,
                    n_opponents: int, n_sims: int = 350) -> float:
    """
    Monte Carlo rollout equity vs n_opponents random hands.
    eval7.evaluate() returns lower scores for stronger hands.
    Returns fraction of pots won (ties = 0.5).
    """
    try:
        my_cards_e7  = [eval7.Card(c) for c in hole_cards]
        board_e7     = [eval7.Card(c) for c in community]

        known  = set(hole_cards + community)
        deck   = [c for c in _ALL_CARDS if c not in known]

        n_board_needed = 5 - len(board_e7)
        # Need: 2*n_opponents cards for opponents + n_board_needed for runout
        cards_needed = 2 * n_opponents + n_board_needed
        if cards_needed > len(deck):
            return 0.5  # Degenerate case

        wins   = 0.0
        trials = 0

        for _ in range(n_sims):
            random.shuffle(deck)
            idx = 0

            # Deal opponent hole cards
            opp_hands = []
            for _ in range(n_opponents):
                opp_hands.append([
                    eval7.Card(deck[idx]),
                    eval7.Card(deck[idx + 1]),
                ])
                idx += 2

            # Complete the board
            runout = board_e7 + [eval7.Card(deck[idx + i]) for i in range(n_board_needed)]

            my_score   = eval7.evaluate(my_cards_e7 + runout)
            best_opp   = min(eval7.evaluate(h + runout) for h in opp_hands)  # min = best hand

            if my_score < best_opp:
                wins += 1.0
            elif my_score == best_opp:
                wins += 0.5
            trials += 1

        return wins / trials if trials > 0 else 0.5

    except Exception:
        return 0.5


# ──────────────────────────────────────────────────────────────────────────────
# AGGRESSION DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def street_aggression(action_log: list, street: str) -> int:
    """Count raises/3-bets on the current street from the log."""
    count = 0
    for entry in action_log:
        if isinstance(entry, dict):
            if entry.get('street') == street and entry.get('action') in ('raise', 'all_in'):
                count += 1
        elif isinstance(entry, str) and 'raise' in entry.lower():
            count += 1
    return count


# ──────────────────────────────────────────────────────────────────────────────
# PREFLOP DECISION
# ──────────────────────────────────────────────────────────────────────────────

def preflop_decision(gs: dict, position: str, n_opponents: int) -> dict:
    cards        = gs['your_cards']
    pot          = gs['pot']
    amount_owed  = gs['amount_owed']
    can_check    = gs['can_check']
    your_stack   = gs['your_stack']
    min_raise_to = gs['min_raise_to']
    action_log   = gs.get('action_log', [])

    score     = hand_score(cards[0], cards[1])
    threshold = preflop_threshold(position, n_opponents)
    n_raises  = street_aggression(action_log, 'preflop')

    # Tighten calling range when facing multiple raises (squeeze situation)
    squeeze_adj = n_raises * 4.0

    # ── Opening (no raise to face) ────────────────────────────────────────────
    if can_check or amount_owed == 0:
        if score >= threshold:
            # Open raise: 2.5x min_raise (standard 6-max open is ~2.2–2.5x BB)
            open_size = min(int(min_raise_to * 1.3), your_stack)
            open_size = max(min_raise_to, open_size)
            return {"action": "raise", "amount": open_size}
        if can_check:
            return {"action": "check"}  # BB takes free flop
        return {"action": "fold"}

    # ── Facing a raise ────────────────────────────────────────────────────────
    # Pot odds required to break even (ignoring implied odds)
    total_pot  = pot + amount_owed
    pot_odds   = amount_owed / total_pot if total_pot > 0 else 1.0

    effective_threshold = threshold + squeeze_adj

    if score >= effective_threshold + 15:
        # Premium hand — 3-bet for value (3x the raise + pot)
        three_bet = min(int(amount_owed * 3 + pot * 0.5), your_stack)
        three_bet = max(min_raise_to, three_bet)
        return {"action": "raise", "amount": three_bet}

    if score >= effective_threshold:
        # Strong enough to call; small overbet only when odds are favourable
        approx_equity = (score - 40) / 100.0  # rough pre-flop equity proxy
        if approx_equity > pot_odds:
            return {"action": "call"}

    # Speculative hands in position with good implied odds
    if score >= threshold - 5 and position in ('BTN', 'CO') and n_raises == 1:
        # Pairs + suited connectors with implied odds: call ~10% pot
        if amount_owed < pot * 0.12:
            return {"action": "call"}

    return {"action": "fold"}


# ──────────────────────────────────────────────────────────────────────────────
# POSTFLOP DECISION
# ──────────────────────────────────────────────────────────────────────────────

def postflop_decision(gs: dict, position: str, n_opponents: int) -> dict:
    cards        = gs['your_cards']
    community    = gs['community_cards']
    pot          = gs['pot']
    amount_owed  = gs['amount_owed']
    can_check    = gs['can_check']
    your_stack   = gs['your_stack']
    min_raise_to = gs['min_raise_to']
    street       = gs['street']
    action_log   = gs.get('action_log', [])

    equity  = estimate_equity(cards, community, n_opponents)
    pos_adj = POS_BONUS.get(position, 0.0)
    eff_eq  = equity + pos_adj

    # Pot odds required to profitably call
    total_pot = pot + amount_owed
    pot_odds  = amount_owed / total_pot if amount_owed > 0 else 0.0

    # Stack-to-pot ratio — drives commitment decisions
    spr = your_stack / pot if pot > 0 else 999.0

    # Aggression adjustment: tighten calling range against heavy action
    n_raises = street_aggression(action_log, street)
    eq_adj   = -0.04 * n_raises   # each raise costs ~4 equity points
    eff_eq  += eq_adj

    # ── Decision thresholds ──────────────────────────────────────────────────
    # These are tuned for 6-max (wider ranges than full ring)
    BLUFF_EQ    = 0.28  # semi-bluff territory  (draws, nut potential)
    CALL_EQ     = 0.38  # clear call vs one opponent
    BET_EQ      = 0.55  # value bet half-pot
    STRONG_EQ   = 0.70  # value bet 3/4 pot
    COMMIT_EQ   = 0.80  # ship it when SPR < 3

    # ── No bet to face — check or bet ────────────────────────────────────────
    if amount_owed == 0:

        if eff_eq >= COMMIT_EQ and spr <= 2:
            return {"action": "all_in"}

        if eff_eq >= STRONG_EQ:
            # 3/4 pot value bet
            bet = int(pot * 0.75)
            bet = max(min_raise_to, min(bet, your_stack))
            return {"action": "raise", "amount": bet}

        if eff_eq >= BET_EQ:
            # Half-pot bet: thin value + protection
            bet = int(pot * 0.50)
            bet = max(min_raise_to, min(bet, your_stack))
            return {"action": "raise", "amount": bet}

        # Occasional semi-bluff on flop/turn with equity and draws
        if eff_eq >= BLUFF_EQ and street in ('flop', 'turn') and position in ('BTN', 'CO'):
            bet = int(pot * 0.40)
            bet = max(min_raise_to, min(bet, your_stack))
            return {"action": "raise", "amount": bet}

        return {"action": "check"}

    # ── Facing a bet — call, raise, or fold ──────────────────────────────────

    # Very strong hand + committed stack → shove
    if eff_eq >= COMMIT_EQ and spr <= 3:
        return {"action": "all_in"}

    # Value raise: re-raise for value when equity is dominant
    if eff_eq >= STRONG_EQ and n_raises < 2:
        raise_to = int(pot + amount_owed * 1.5)
        raise_to = max(min_raise_to, min(raise_to, your_stack))
        return {"action": "raise", "amount": raise_to}

    # Clear call: equity beats the pot odds required
    if eff_eq >= CALL_EQ or eff_eq > pot_odds + 0.03:
        return {"action": "call"}

    # Implied-odds call: in position, drawing hand (30–38% equity), large SPR
    # We can win more on later streets if we hit
    if BLUFF_EQ <= eff_eq < CALL_EQ and position in ('BTN', 'CO') and spr > 4:
        implied_ratio = your_stack / amount_owed if amount_owed > 0 else 0
        if implied_ratio >= 6:
            return {"action": "call"}

    # Pure pot-odds call: never call when we're a big dog
    if eff_eq > pot_odds:
        return {"action": "call"}

    return {"action": "fold"}


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def decide(game_state: dict) -> dict:
    """
    Called once per action by the Fullhouse engine.
    Returns one of: fold / check / call / raise / all_in.
    """
    try:
        players    = game_state.get('players', [])
        position   = detect_position(players)
        n_opp      = count_active_opponents(players)
        street     = game_state.get('street', 'preflop')

        if street == 'preflop':
            return preflop_decision(game_state, position, n_opp)
        else:
            return postflop_decision(game_state, position, n_opp)

    except Exception:
        # Engine catches exceptions at a higher level, but safety-net here too
        if game_state.get('can_check'):
            return {"action": "check"}
        return {"action": "fold"}