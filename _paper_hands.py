"""Paper-hand verifications for skantbot 7.10.

Per advisor: verify the FOLD direction AND the CALL direction. The
critical risk is over-folding from fix 3 dropping the suited hand-class
when emitting a flush combo.

Cases:
  A. Hand 27 (KK22 vs jam on 3-flush) -> must FOLD  (the bust we're fixing)
  B. Nut flush vs same jam              -> must CALL (anti-overfold check)
  C. Top set on flush board vs jam      -> equity ~25-30%, likely FOLD
  D. Hand 3 river bet (J-high vs CS)    -> unchanged from pre-fix
  E. 3-bet pot scenario (aggressors=2)  -> still picks QQ+/AKs range
"""
import sys, random, importlib.util
sys.path.insert(0, ".")


def load(path):
    spec = importlib.util.spec_from_file_location("bm", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def state_27(hole=("Kh", "2s")):
    SB, BB, UTG, ME, CO = 3, 4, 0, 1, 2
    return {
        "type": "action_request", "hand_id": "h0027", "street": "turn",
        "seat_to_act": ME, "pot": 12815,
        "community_cards": ["2c", "Jh", "Kc", "7c"],
        "current_bet": 10128, "min_raise_to": 18969,
        "amount_owed": 8841, "can_check": False,
        "your_cards": list(hole), "your_stack": 8498,
        "your_bet_this_street": 1287,
        "players": [
            {"seat": UTG, "bot_id": "deepseek-10", "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": ME,  "bot_id": "skantbot7.10", "is_folded": False, "is_all_in": False, "stack": 8498},
            {"seat": CO,  "bot_id": "chatgpt-7",   "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": SB,  "bot_id": "chatgpt-2",   "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": BB,  "bot_id": "human",       "is_folded": False, "is_all_in": True, "stack": 0},
        ],
        "action_log": [
            {"seat": SB, "action": "small_blind", "amount": 50},
            {"seat": BB, "action": "big_blind",   "amount": 100},
            {"seat": UTG,"action": "raise",       "amount": 250},
            {"seat": ME, "action": "call",        "amount": 250},
            {"seat": CO, "action": "fold",        "amount": 0},
            {"seat": SB, "action": "fold",        "amount": 0},
            {"seat": BB, "action": "call",        "amount": 250},
            {"seat": BB, "action": "raise",       "amount": 300},
            {"seat": UTG,"action": "fold",        "amount": 0},
            {"seat": ME, "action": "call",        "amount": 300},
            {"seat": BB, "action": "check",       "amount": 0},
            {"seat": ME, "action": "raise",       "amount": 1287},
            {"seat": BB, "action": "all_in",      "amount": 10128},
        ],
    }


def measure(bot, state, label):
    pos = bot.get_position_label(state)
    cfg = bot.CONFIG
    action = bot.decide_postflop(state, pos, cfg, random.Random(42))
    BB = 4
    if bot.find_aggressor_seat(state) is not None:
        v_range = bot.aggressor_likely_range(state, BB)
        nz = {k: v for k, v in v_range.items() if v > 0}
        eq = bot.equity_vs_range(state["your_cards"], state["community_cards"],
                                 v_range, n_sims=3000, rng=random.Random(42))
    else:
        nz, eq = {}, None
    eff = min(state["amount_owed"], state["your_stack"])
    callable_pot = state["pot"] - (state["amount_owed"] - eff)
    pot_odds = eff / (callable_pot + eff)
    risk_pct = bot.stack_risked_pct(state, eff)
    required = pot_odds + cfg.pot_odds_buffer_normal + cfg.variance_c * (risk_pct ** 2)
    print(f"\n  {label}")
    print(f"    hole       : {state['your_cards']}   board: {state['community_cards']}")
    print(f"    range size : {len(nz)}")
    print(f"    equity     : {eq*100:.1f}%   required: {required*100:.1f}%   action: {action['action']}")
    return action


def main():
    bot_10 = load("bots/skantbot7.10/bot.py")
    bot_09 = load("bots/skantbot7.9/bot.py")

    print("=" * 72)
    print("PAPER HAND A — KK22 vs jam (the hand 27 bust)")
    print("Expected: 7.10 FOLDS, 7.9 (unfixed) CALLS")
    print("=" * 72)
    a10 = measure(bot_10, state_27(("Kh", "2s")), "7.10")
    a09 = measure(bot_09, state_27(("Kh", "2s")), "7.9 (baseline)")
    assert a10["action"] == "fold", f"FAIL: 7.10 should FOLD hand 27, got {a10}"
    assert a09["action"] == "call", f"FAIL: 7.9 baseline should CALL hand 27, got {a09}"

    print()
    print("=" * 72)
    print("PAPER HAND B — Nut flush vs jam (must CALL)")
    print("Hole: AcXc (made flush) on Kc-Jh-2c-7c, facing same all-in")
    print("=" * 72)
    # Pick Ac3c so it doesn't conflict with anyone's range. Hole Ac3c on Kc-Jh-2c-7c
    # = nut flush. Should snap-call.
    b10 = measure(bot_10, state_27(("Ac", "3c")), "7.10 (nut flush)")
    b09 = measure(bot_09, state_27(("Ac", "3c")), "7.9 baseline")
    assert b10["action"] in ("call", "raise"), f"FAIL: 7.10 must CALL nut flush, got {b10}"

    print()
    print("=" * 72)
    print("PAPER HAND C — Top set (KsKd) vs jam on flush board")
    print("Should expose whether dropping suited hand-class over-folds top sets")
    print("=" * 72)
    c10 = measure(bot_10, state_27(("Ks", "Kd")), "7.10 (top set)")
    c09 = measure(bot_09, state_27(("Ks", "Kd")), "7.9 baseline (top set)")
    # Set vs flush is ~25% equity vs flush, ~85% vs lower set, ~95% vs pair.
    # Likely FOLD against a polarized jam range — but verify equity is sane.

    print()
    print("=" * 72)
    print("PAPER HAND D — Hand 3 river bet (J-high vs station)")
    print("Bot is the aggressor; agg_seat narrowing not used. Expected: identical")
    print("decision between 7.9 and 7.10 (different code path = our fix doesn't")
    print("touch this).")
    print("=" * 72)
    # Reconstruct hand 3 state at river bet decision.
    # Simplified 4-handed (the table shown in user's log):
    #   push_fold SB, human BB, loose_passive, overbet_bot, skantbot7.9 (raise),
    #   push_fold and human fold, calling_station calls.
    # By river, only skant and CS in. Skant is to_act on river facing CS check.
    # Skantbot's position: CO/BTN (acts after CS who is BB).
    # Pot at river ≈ 351 (preflop) + 200+200 (flop) + 0 (turn check check) = 922.
    SB_S, BB_S, ME_S = 0, 1, 5  # arbitrary seat numbers
    state_3 = {
        "type": "action_request", "hand_id": "h0003", "street": "river",
        "seat_to_act": ME_S, "pot": 922,
        "community_cards": ["8c", "6h", "3h", "2s", "9c"],
        "current_bet": 0, "min_raise_to": 100,
        "amount_owed": 0, "can_check": True,
        "your_cards": ["Jd", "Td"], "your_stack": 13639,
        "your_bet_this_street": 0,
        "players": [
            {"seat": SB_S, "bot_id": "push_fold",  "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": 1,    "bot_id": "human",      "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": 2,    "bot_id": "loose_passive", "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": 3,    "bot_id": "overbet_bot",   "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": ME_S, "bot_id": "skantbot7.10",  "is_folded": False, "is_all_in": False, "stack": 13639},
            {"seat": 4,    "bot_id": "calling_station", "is_folded": False, "is_all_in": False, "stack": 5861},
        ],
        "action_log": [
            {"seat": SB_S, "action": "small_blind", "amount": 50},
            {"seat": 1, "action": "big_blind", "amount": 100},
            {"seat": 2, "action": "fold", "amount": 0},
            {"seat": 3, "action": "fold", "amount": 0},
            {"seat": ME_S, "action": "raise", "amount": 201},
            {"seat": SB_S, "action": "fold", "amount": 0},
            {"seat": 1, "action": "fold", "amount": 0},
            {"seat": 4, "action": "call", "amount": 101},
            {"seat": 4, "action": "check", "amount": 0},
            {"seat": ME_S, "action": "raise", "amount": 260},
            {"seat": 4, "action": "call", "amount": 260},
            {"seat": 4, "action": "check", "amount": 0},
            {"seat": ME_S, "action": "check", "amount": 0},
            {"seat": 4, "action": "check", "amount": 0},
        ],
    }
    print("\n  7.10 hand 3 river decision:")
    a3_10 = bot_10.decide(state_3)
    print(f"    action: {a3_10}")
    print("  7.9 hand 3 river decision:")
    a3_09 = bot_09.decide(state_3)
    print(f"    action: {a3_09}")
    # Soft check: actions should match (same code path)
    if a3_10 != a3_09:
        print(f"  WARN: 7.10 and 7.9 differ on hand 3. {a3_10} vs {a3_09}")
        print("  May indicate Fix 1 has wider effect than expected.")
    else:
        print(f"  ✓ MATCH ({a3_10})")

    print()
    print("=" * 72)
    print("PAPER HAND E — 3-bet pot scenario (aggressors == 2)")
    print("Verify our fix doesn't break the existing 3-bet narrow path")
    print("=" * 72)
    # 3-bet pot HU: human raises, skant 3-bets, human calls.
    # Postflop human leads. agg_seat = human, aggressors = 2 (both raised).
    SB2, BB2 = 0, 1
    state_3bet = {
        "type": "action_request", "hand_id": "h_3bet", "street": "flop",
        "seat_to_act": SB2, "pot": 1200,
        "community_cards": ["As", "Ks", "9d"],
        "current_bet": 200, "min_raise_to": 400,
        "amount_owed": 200, "can_check": False,
        "your_cards": ["Qh", "Qd"], "your_stack": 9000,
        "your_bet_this_street": 0,
        "players": [
            {"seat": SB2, "bot_id": "skantbot7.10", "is_folded": False, "is_all_in": False, "stack": 9000},
            {"seat": BB2, "bot_id": "human", "is_folded": False, "is_all_in": False, "stack": 9000},
        ],
        "action_log": [
            {"seat": SB2, "action": "small_blind", "amount": 50},
            {"seat": BB2, "action": "big_blind", "amount": 100},
            {"seat": SB2, "action": "raise", "amount": 250},
            {"seat": BB2, "action": "raise", "amount": 750},
            {"seat": SB2, "action": "call",  "amount": 750},
            {"seat": BB2, "action": "raise", "amount": 200},
        ],
    }
    pos_3bet = bot_10.get_position_label(state_3bet)
    agg_seat = bot_10.find_aggressor_seat(state_3bet)
    aggressors_count = bot_10.count_aggressors(state_3bet)
    v_range = bot_10.aggressor_likely_range(state_3bet, agg_seat)
    nz = list(v_range.keys())[:15]
    print(f"\n  position: {pos_3bet}, agg_seat: {agg_seat}, count_aggressors: {aggressors_count}")
    print(f"  base range (first 15): {nz}")
    # Expected: tight QQ+/AKs range. Should include AA, KK, QQ, AKs, AKo, A5s — NOT
    # weak suited hands like 87s.
    expected = {"AA", "KK", "QQ", "AKs", "AKo", "A5s"}
    actual_set = set(v_range.keys())
    assert expected.issubset(actual_set), \
        f"FAIL: 3-bet narrow missing premiums. Expected {expected}, got {actual_set}"
    forbidden = {"87s", "76s", "65s", "J9s"}
    leaked = forbidden & actual_set
    assert not leaked, f"FAIL: 3-bet narrow has weak hands {leaked}, base range too wide"
    print(f"  ✓ contains QQ+/AKs class; does not contain weak suited hands.")

    print("\n" + "=" * 72)
    print("All paper-hand assertions passed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
