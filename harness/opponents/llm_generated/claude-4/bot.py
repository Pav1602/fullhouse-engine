"""
TAG Bot — Tight-Aggressive 6-max NLHE
Fullhouse Engine · Quadrature Capital Hackathon 2026

Architecture
─────────────
Preflop  : Tiered hand ranges (5 tiers), position-aware opening/3-bet logic,
           BB-estimated sizing.
Postflop : Monte Carlo equity via eval7 (400 sims, ~0.3–0.5 s),
           draw-aware pot odds, SPR-based commitment threshold,
           semi-bluff frequency calibrated by position + street.

Key design decisions
────────────────────
• amount in raise = total bet, not raise-by (engine spec)
• Whole function wrapped in try/except → never auto-folds on a crash
• eval7 Card strings accept "As", "Kh", "Tc" directly (matches engine format)
• eval7.evaluate: lower integer = better hand
"""

import random
import eval7  # provided by engine


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def decide(game_state: dict) -> dict:
    try:
        return _decide(game_state)
    except Exception:
        return {"action": "check"} if game_state.get("can_check") else {"action": "fold"}


def _decide(gs: dict) -> dict:
    cards     = gs["your_cards"]          # ["As", "Kh"]
    board     = gs.get("community_cards", [])
    street    = gs.get("street", "preflop")
    pot       = gs.get("pot", 0)
    stack     = gs.get("your_stack", 0)
    owed      = gs.get("amount_owed", 0)
    can_check = gs.get("can_check", False)
    min_raise = gs.get("min_raise_to", 0)
    players   = gs.get("players", [])
    log       = gs.get("action_log", [])

    n_active  = sum(1 for p in players if not p.get("folded", False))
    position  = estimate_position(log, len(players))   # 0=EP, 1=MP, 2=LP/blind

    if street == "preflop":
        return _preflop(cards, owed, pot, can_check, min_raise,
                        stack, position, log, n_active)
    return _postflop(cards, board, street, pot, owed, can_check,
                     min_raise, stack, position, n_active)


# ═══════════════════════════════════════════════════════════════════════════════
#  POSITION ESTIMATION
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_position(log: list, n_seats: int) -> int:
    """
    Infer position from the preflop action log.

    Counts voluntary preflop actions before our first action.
    Blind posts (post_sb / post_bb / "post") are excluded.
    Returns 0 (early), 1 (middle), 2 (late / blind).
    """
    BLIND_ACTIONS = {"post_sb", "post_bb", "small_blind", "big_blind", "post"}

    if n_seats <= 3:
        return 2  # short-handed: play loose

    voluntary_before = 0
    for action in log:
        if action.get("street", "preflop") != "preflop":
            break
        act = action.get("action", "")
        if act in BLIND_ACTIONS:
            continue
        if action.get("is_me") or action.get("you"):
            break
        voluntary_before += 1

    if voluntary_before == 0:
        return 0   # UTG / early
    if voluntary_before <= 2:
        return 1   # HJ / MP
    return 2       # CO / BTN / SB / BB


# ═══════════════════════════════════════════════════════════════════════════════
#  PREFLOP
# ═══════════════════════════════════════════════════════════════════════════════

_RV = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,
       '9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}


def hand_tier(cards: list) -> int:
    """
    Classify hole cards into 5 tiers.

    Tier 1 — Premium   : JJ+, AK
    Tier 2 — Strong    : 99-TT, AJs/AQs, AQo, KQs
    Tier 3 — Playable  : 66-88, A2s-ATs, AJo/ATo, KJs, QJs, JTs, KQo
    Tier 4 — Speculative: 22-55, suited connectors/gappers (54s+), KTs/QTs/J9s
    Tier 5 — Trash     : everything else
    """
    r1, s1 = cards[0][:-1], cards[0][-1]
    r2, s2 = cards[1][:-1], cards[1][-1]
    v1, v2 = _RV.get(r1, 0), _RV.get(r2, 0)

    # Normalise so high card is r1/v1
    if v1 < v2:
        r1, r2, v1, v2, s1, s2 = r2, r1, v2, v1, s2, s1

    suited = s1 == s2
    pair   = r1 == r2

    # ── Tier 1 ──────────────────────────────────────────────────────────────
    if pair and v1 >= 11:               return 1  # JJ, QQ, KK, AA
    if r1 == 'A' and r2 == 'K':        return 1  # AKs, AKo

    # ── Tier 2 ──────────────────────────────────────────────────────────────
    if pair and v1 >= 9:                return 2  # 99, TT
    if r1 == 'A' and v2 >= 11 and suited: return 2  # AJs, AQs
    if r1 == 'A' and r2 == 'Q':        return 2  # AQo
    if r1 == 'K' and r2 == 'Q' and suited: return 2  # KQs

    # ── Tier 3 ──────────────────────────────────────────────────────────────
    if pair and v1 >= 6:                return 3  # 66, 77, 88
    if r1 == 'A' and suited:            return 3  # A2s–ATs
    if r1 == 'A' and v2 >= 9:          return 3  # ATo, AJo
    if r1 == 'K' and r2 == 'Q':        return 3  # KQo
    if suited and v1 >= 11 and v2 >= 10: return 3  # KJs, QJs, JTs (any)
    if suited and v1 == 11 and v2 == 10: return 3  # explicit JTs

    # ── Tier 4 ──────────────────────────────────────────────────────────────
    if pair:                            return 4  # 22–55
    if suited and 1 <= v1 - v2 <= 2 and v2 >= 5: return 4  # suited connectors / 1-gappers 54s+
    if suited and v1 >= 10 and v2 >= 8: return 4  # KTs, QTs, J9s, T8s

    return 5


def _preflop(cards, owed, pot, can_check, min_raise, stack, position, log, n_active):
    tier = hand_tier(cards)

    # Preflop raises by opponents before our action
    opp_raises = [a for a in log
                  if a.get("street", "preflop") == "preflop"
                  and a.get("action") == "raise"
                  and not (a.get("is_me") or a.get("you"))]
    n_raises = len(opp_raises)

    # Estimate BB.  preflop min_raise ≈ 2 BB; fall back to pot heuristic.
    bb = max(min_raise // 2, 1) if min_raise >= 2 else max(pot // max(n_active, 1), 50)

    # ── Facing 3-bet or more (n_raises ≥ 2) ────────────────────────────────
    if n_raises >= 2:
        if tier == 1:
            if owed >= stack * 0.25:
                return {"action": "all_in"}
            # 4-bet to ~2.5x the 3-bet
            raise_to = _clamp(int(min_raise * 2.5), min_raise, stack)
            return {"action": "raise", "amount": raise_to}
        return {"action": "fold"}

    # ── Facing one raise (3-bet opportunity) ───────────────────────────────
    if n_raises == 1:
        if tier == 1:
            # 3-bet to ~3x open
            raise_to = _clamp(int(min_raise * 3), min_raise, stack)
            return {"action": "raise", "amount": raise_to}
        if tier == 2 and owed < pot * 0.35:
            return {"action": "call"}
        if tier == 3 and position == 2 and owed < pot * 0.20:
            return {"action": "call"}  # speculative call in position only
        return {"action": "fold"}

    # ── No raise yet: first-in open or BB option ────────────────────────────
    # Loosen up as we get later: EP opens tier ≤ 2, MP ≤ 3, LP ≤ 4
    open_threshold = {0: 2, 1: 3, 2: 4}[position]

    if tier <= open_threshold:
        # Open to 2.5 BB; snap to min_raise if bigger
        raise_to = _clamp(int(bb * 2.5), min_raise, stack)
        return {"action": "raise", "amount": raise_to}

    # We're in the BB with a walk or nobody raised
    if can_check:
        if tier == 4:
            return {"action": "check"}  # playable speculative for free
        return {"action": "check"}

    # Complete a limp if we're getting a great price on a speculative hand
    if owed <= bb and tier <= 4:
        return {"action": "call"}

    return {"action": "fold"}


# ═══════════════════════════════════════════════════════════════════════════════
#  POSTFLOP
# ═══════════════════════════════════════════════════════════════════════════════

def mc_equity(hole: list, board: list, n_opp: int = 1, sims: int = 400) -> float:
    """
    Monte Carlo equity estimate using eval7.

    Deals random runouts + opponent hole cards, tallies win/split frequency.
    Runs in ≈ 0.35 s for 400 sims on a 0.5-core budget — well within 2 s limit.
    """
    try:
        h = [eval7.Card(c) for c in hole]
        b = [eval7.Card(c) for c in board]
        dead = set(h + b)

        deck = [
            eval7.Card(r + s)
            for r in "23456789TJQKA"
            for s in "cdhs"
            if eval7.Card(r + s) not in dead
        ]

        cards_needed = 5 - len(b)
        wins = ties = total = 0

        for _ in range(sims):
            random.shuffle(deck)
            idx = 0

            opps = [deck[idx + i*2 : idx + i*2 + 2] for i in range(n_opp)]
            idx += n_opp * 2
            runout = deck[idx : idx + cards_needed]

            if any(len(o) < 2 for o in opps) or len(runout) < cards_needed:
                continue

            final_board = b + runout
            my_val  = eval7.evaluate(h + final_board)
            opp_val = min(eval7.evaluate(o + final_board) for o in opps)

            if my_val < opp_val:
                wins += 1
            elif my_val == opp_val:
                ties += 0.5
            total += 1

        return (wins + ties) / total if total else 0.5
    except Exception:
        return 0.5


def draw_equity(hole: list, board: list) -> tuple:
    """
    Detect flush / straight draws and return (has_draw, equity_estimate).

    Outs-based approximation using the Rule of 4 / 2:
      Flop  (2 cards to come) : multiply outs by 4  → probability
      Turn  (1 card to come)  : multiply outs by 2
    """
    try:
        all_cards = hole + board
        suits  = [c[-1] for c in all_cards]
        ranks  = sorted(set(_RV[c[:-1]] for c in all_cards if c[:-1] in _RV))
        to_go  = 5 - len(board)  # 2 on flop, 1 on turn

        # ── Flush draw (9 outs) ─────────────────────────────────────────────
        for suit in "cdhs":
            if suits.count(suit) == 4:
                pct = 9 * (4 if to_go == 2 else 2) / 100
                return True, min(pct, 0.40)

        # ── Open-ended straight draw (8 outs) ──────────────────────────────
        for i in range(len(ranks) - 3):
            if ranks[i+3] - ranks[i] == 3:  # 4 consecutive
                pct = 8 * (4 if to_go == 2 else 2) / 100
                return True, min(pct, 0.35)

        # ── Gutshot (4 outs) ────────────────────────────────────────────────
        for i in range(len(ranks) - 3):
            if ranks[i+3] - ranks[i] == 4:  # gap in 4-card window
                pct = 4 * (4 if to_go == 2 else 2) / 100
                return True, min(pct, 0.18)

        return False, 0.0
    except Exception:
        return False, 0.0


def _postflop(cards, board, street, pot, owed, can_check, min_raise, stack, position, n_active):
    n_opp = max(1, n_active - 1)
    equity = mc_equity(cards, board, n_opp, sims=400)

    has_draw, d_eq = draw_equity(cards, board)
    eff_equity  = max(equity, d_eq) if has_draw else equity

    pot_odds = owed / (pot + owed) if owed > 0 else 0
    spr      = stack / max(pot, 1)
    committing = spr < 2.5  # low SPR → just get it in

    # ── Facing a bet ────────────────────────────────────────────────────────
    if owed > 0:

        if equity >= 0.72:
            # Near-nut hand: raise or shove
            raise_to = _clamp(int(pot * 0.9 + owed), min_raise, stack)
            if raise_to >= stack * 0.80 or committing:
                return {"action": "all_in"}
            return {"action": "raise", "amount": raise_to}

        if equity >= 0.55:
            # Strong hand: call; shove if committed
            if committing and equity >= 0.60:
                return {"action": "all_in"}
            return {"action": "call"}

        if eff_equity >= 0.38:
            # Medium hand or strong draw: call if pot odds justify
            if pot_odds < eff_equity - 0.04:
                return {"action": "call"}
            return {"action": "fold"}

        if equity >= 0.28 and pot_odds < 0.20:
            # Very cheap price on a marginal holding
            return {"action": "call"}

        return {"action": "fold"}

    # ── No bet facing us (bet / check decision) ──────────────────────────────
    if equity >= 0.66:
        # Value bet: ~65% pot
        bet = _clamp(int(pot * 0.65), min_raise, stack)
        if committing:
            return {"action": "all_in"}
        return {"action": "raise", "amount": bet}

    if equity >= 0.52 and position == 2:
        # Thin value in position: ~50% pot
        bet = _clamp(int(pot * 0.50), min_raise, stack)
        return {"action": "raise", "amount": bet}

    if equity >= 0.48 and street == "flop" and n_active == 2:
        # HU c-bet with any decent equity: ~45% pot
        bet = _clamp(int(pot * 0.45), min_raise, stack)
        return {"action": "raise", "amount": bet}

    if has_draw and street != "river" and position == 2:
        # Semi-bluff in position: 55% frequency
        if random.random() < 0.55:
            bet = _clamp(int(pot * 0.55), min_raise, stack)
            return {"action": "raise", "amount": bet}
        return {"action": "check"}

    if has_draw and street != "river" and position != 2:
        # Out of position draw: check more, bluff less
        if random.random() < 0.25:
            bet = _clamp(int(pot * 0.50), min_raise, stack)
            return {"action": "raise", "amount": bet}
        return {"action": "check"}

    return {"action": "check"}


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))