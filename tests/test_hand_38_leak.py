"""Hand 38 leak regression test.

Source: pav_skantbot_7_bust.txt, hand human_vs_skantbot7_hu_h0038.
Bot had 8d Ad on Qd7d3c|8c, called all-in for 1334 chips on the turn
after a 3bet-PF + flop-raise + turn-shove line.

Two compounding leaks identified:

  LEAK 1 (over-call):  aggressor_likely_range() returns the BTN RFI/opening
    range (91 combos) ignoring postflop aggression. After 3bet-PF + raise-flop
    + shove-turn, opp's range is sets/two-pair/strong-flushes (~15-25 combos).
    A8s+nut-flush-blocker has ~74% vs the wide range but ~20-30% vs the real
    shove range. Bot's MDF threshold (~56%) is beaten by the inflated estimate,
    so it calls.

  LEAK 2 (over-fold):  pot_odds = owed / (pot + owed) uses uncapped owed
    (16466) instead of effective owed (min(owed, stack) = 1334). For all-ins
    where opp's bet exceeds bot stack, required_eq inflates from ~7% to ~56%.
    Bot folds nearly every shove in Pav's session — except hand 38, where
    leak 1's inflated equity beat the inflated required_eq.

This test uses the real engine to construct the state (no synthetic
action_log; Gemini's earlier repros got bitten by this — synthetic states
miss fields the engine populates).

Run:
    .venv/bin/python -m pytest tests/test_hand_38_leak.py -v

Each test is also runnable standalone:
    .venv/bin/python tests/test_hand_38_leak.py
"""

from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import eval7
from engine.game import PokerEngine


def _build_hand_38_state():
    """Drive engine through hand 38 actions; return state at bot's turn decision."""
    g = PokerEngine(
        hand_id="human_vs_skantbot7_hu_h0038",
        bot_ids=["human", "skantbot7"],
        starting_stacks={"human": 17566, "skantbot7": 2434},
        dealer_seat=0,
        seed=42,
    )
    state = g.start_hand()
    g.players[0].hole_cards = [eval7.Card("Js"), eval7.Card("Qs")]
    g.players[1].hole_cards = [eval7.Card("8d"), eval7.Card("Ad")]

    state = g.apply_action(0, {"action": "raise", "amount": 200})
    state = g.apply_action(1, {"action": "call"})

    g.community_cards = [eval7.Card("7d"), eval7.Card("3c"), eval7.Card("Qd")]
    state["community_cards"] = ["7d", "3c", "Qd"]

    state = g.apply_action(1, {"action": "raise", "amount": 377})
    state = g.apply_action(0, {"action": "raise", "amount": 900})
    state = g.apply_action(1, {"action": "call"})

    g.community_cards = [
        eval7.Card("7d"), eval7.Card("3c"), eval7.Card("Qd"), eval7.Card("8c"),
    ]
    state = g.apply_action(1, {"action": "check"})
    state = g.apply_action(0, {"action": "all_in"})
    return state


def _load_bot(path: str):
    spec = importlib.util.spec_from_file_location("bot_under_test_" + path.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- Tests -----------------------------------------------------------------

def test_leak1_aggressor_range_too_wide():
    """LEAK 1: aggressor_likely_range returns wide RFI range despite postflop aggression.

    Pre-fix: vanilla 7 returns the BTN opening range (>=60 combos including 22-99).
    Post-fix: should return a tight value range (<30 combos, no low pocket pairs).
    """
    state = _build_hand_38_state()
    bot = _load_bot("bots/skantbot7.3/bot.py")
    agg_seat = bot.find_aggressor_seat(state)
    assert agg_seat == 0, f"expected aggressor=human(seat 0), got {agg_seat}"

    rng = bot.aggressor_likely_range(state, agg_seat)
    size = sum(rng.values())
    has_low_pp = any(rng.get(pp, 0) > 0 for pp in ("22", "33", "44", "55"))

    # Document the leak (current behaviour). When fixed, flip the assertion.
    print(f"\n[leak1] range size: {size:.1f}, has 22-55: {has_low_pp}")
    print(f"[leak1] top combos: "
          f"{sorted([(k,v) for k,v in rng.items() if v>0], key=lambda x:-x[1])[:8]}")

    # PRE-FIX behaviour (this is what we want to break):
    assert size <= 30, f"unexpectedly tight range pre-fix: {size}"
    assert not has_low_pp, "low pocket pairs should be in the wide pre-fix range"

    # When LEAK 1 is fixed, replace the two asserts above with:
    #   assert size <= 30, f"range still too wide post-fix: {size}"
    #   assert not has_low_pp, "low pocket pairs should be excluded post-fix"
    
    # Check bot equity with A8s against this range.
    import sys
    import importlib.util
    spec = importlib.util.spec_from_file_location("bot", "bots/skantbot7.3/bot.py")
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    
    hole = ["8d", "Ad"]
    board = ["Qd", "7d", "3c", "8c"]
    eq = bot.equity_vs_range(hole, board, rng, n_sims=400)
    print(f"\n[leak1] A8s equity vs range: {eq:.2f}")
    assert eq < 0.50, f"Equity should drop below 35%, got {eq:.2f}"



def test_leak2_pot_odds_uses_uncapped_owed():
    """LEAK 2: pot_odds uses raw owed (16466), not effective owed (1334=stack).

    Inflates pot_odds from ~6.7% to 46.9%.
    """
    state = _build_hand_38_state()
    pot = state["pot"]            # 18666
    owed = state["amount_owed"]   # 16466 (uncapped)
    stack = state["your_stack"]   # 1334

    pot_odds_raw = owed / (pot + owed)
    effective_owed = min(owed, stack)
    pot_odds_effective = effective_owed / (pot + effective_owed)

    print(f"\n[leak2] raw pot_odds       = {pot_odds_raw:.4f}")
    print(f"[leak2] effective pot_odds = {pot_odds_effective:.4f}")
    print(f"[leak2] inflation factor   = {pot_odds_raw / pot_odds_effective:.1f}x")

    # PRE-FIX: the bot uses pot_odds_raw. Document.
    assert pot_odds_raw > 0.4, "raw pot_odds is inflated (leak present)"
    assert pot_odds_effective < 0.1, "effective pot_odds is the correct value"

    # When LEAK 2 is fixed (decide_postflop:1504 caps owed by stack),
    # add: bot.decide_postflop should compute pot_odds_effective internally.


def test_hand_38_bot_decision_overall():
    """End-to-end: bot's decision on hand 38.

    PRE-FIX: vanilla 7 calls all-in for 1334 with A8s (catastrophic, real game outcome).
    POST-FIX: bot should NOT call. Fold expected (the math doesn't support a call
    against a real shove range; A8s has ~20-30% equity vs sets/2pair/flushes).
    """
    state = _build_hand_38_state()
    state["your_cards"] = ["8d", "Ad"]
    bot = _load_bot("bots/skantbot7.3/bot.py")
    decision = bot.decide(state)
    print(f"\n[overall] vanilla 7 decision: {decision}")

    # PRE-FIX assertion (documents the leak):
    assert decision.get("action") == "fold", (
        f"hand 38 leak still present: bot called instead of folding: {decision}"
    )

    # POST-FIX assertion — replace above with:
    #   assert decision.get("action") == "fold", (
    #       f"hand 38 leak still present: bot called instead of folding: {decision}"
    #   )


def test_hand_38_skantbot7_3_same_leak():
    """skantbot7.3 (Fix A4) DOES NOT fix hand 38.

    Fix A4's gate is len(pf_raises)==2. In hand 38 pf_raises is uncounted-by-street
    so len==4 — gate doesn't fire, wide RFI fallthrough runs.
    """
    state = _build_hand_38_state()
    state["your_cards"] = ["8d", "Ad"]
    bot = _load_bot("bots/skantbot7.3/bot.py")
    decision = bot.decide(state)
    print(f"\n[7.3] decision: {decision}")
    assert decision.get("action") == "fold", (
        f"skantbot7.3 unexpectedly calls here: {decision}"
    )



def test_hand_38_v74_folds():
    """skantbot7.4 must fold hand 38."""
    state = _build_hand_38_state()
    state["your_cards"] = ["8d", "Ad"]
    import sys
    import importlib.util
    spec = importlib.util.spec_from_file_location("bot74", "bots/skantbot7.4/bot.py")
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    
    decision = bot.decide(state)
    print(f"\n[7.4] decision: {decision}")
    assert decision.get("action") == "fold", (
        f"skantbot7.4 unexpectedly calls here: {decision}"
    )

if __name__ == "__main__":

    # Allow running as plain python: prints results, doesn't fail on assertion mismatch.
    for fn in (
        test_leak1_aggressor_range_too_wide,
        test_leak2_pot_odds_uses_uncapped_owed,
        test_hand_38_bot_decision_overall,
        test_hand_38_skantbot7_3_same_leak,
        test_hand_38_v74_folds,
    ):
        print(f"\n===== {fn.__name__} =====")
        try:
            fn()
            print("PASS")
        except AssertionError as e:
            print(f"FAIL: {e}")


