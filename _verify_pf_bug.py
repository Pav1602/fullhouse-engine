"""Verify the hypothesis: `_preflop_action_log` returns the full hand log
when folded players leave partial bets that never equalize, causing
`count_postflop_raises` to return 0 and skipping range narrowing.

Test: patch the function to use only ACTIVE (non-folded) players, re-run the
trace, see if narrowing now activates."""
import sys, random
sys.path.insert(0, ".")

import importlib.util
spec = importlib.util.spec_from_file_location("skb79", "bots/skantbot7.9/bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def patched_preflop_action_log(state):
    """Fixed version: track who has FOLDED, exclude their bets from the
    equalization check so partial blinds/calls from folders don't keep the
    loop running into postflop streets."""
    log = state.get("action_log", [])
    pf = []
    bets = {}       # seat -> total this street
    folded = set()
    saw_voluntary = False
    in_pf = True
    for e in log:
        if not in_pf:
            break
        seat = e.get("seat")
        action = e.get("action")
        amt = e.get("amount", 0)
        pf.append(e)
        if action in ("small_blind", "big_blind"):
            bets[seat] = amt
            continue
        if action == "fold":
            folded.add(seat)
            continue
        saw_voluntary = True
        if action in ("raise", "all_in"):
            bets[seat] = amt
        elif action == "call":
            bets[seat] = max(bets.values())
        elif action == "check":
            pass

        # Equalization check excludes folded seats
        active_bets = [v for s, v in bets.items() if s not in folded]
        if saw_voluntary and len(active_bets) >= 2:
            if all(v == active_bets[0] for v in active_bets):
                in_pf = False
                break
    return pf


# Build hand-27 turn state (same as _trace_hand27.py)
def build_turn_state():
    SB, BB, UTG, ME, CO = 3, 4, 0, 1, 2
    return {
        "type": "action_request",
        "hand_id": "human_vs_skantbot7.9_6max_h0027",
        "street": "turn",
        "seat_to_act": ME,
        "pot": 1400 + 1287 + 10128,
        "community_cards": ["2c", "Jh", "Kc", "7c"],
        "current_bet": 10128,
        "min_raise_to": 10128 + 8841,
        "amount_owed": 8841,
        "can_check": False,
        "your_cards": ["Kh", "2s"],
        "your_stack": 8498,
        "your_bet_this_street": 1287,
        "players": [
            {"seat": UTG, "bot_id": "deepseek-10", "is_folded": True,  "is_all_in": False, "stack": 0},
            {"seat": ME,  "bot_id": "skantbot7.9", "is_folded": False, "is_all_in": False, "stack": 8498},
            {"seat": CO,  "bot_id": "chatgpt-7",   "is_folded": True,  "is_all_in": False, "stack": 0},
            {"seat": SB,  "bot_id": "chatgpt-2",   "is_folded": True,  "is_all_in": False, "stack": 0},
            {"seat": BB,  "bot_id": "human",       "is_folded": False, "is_all_in": True,  "stack": 0},
        ],
        "action_log": [
            {"seat": SB,  "action": "small_blind", "amount": 50},
            {"seat": BB,  "action": "big_blind",   "amount": 100},
            {"seat": UTG, "action": "raise",       "amount": 250},
            {"seat": ME,  "action": "call",        "amount": 250},
            {"seat": CO,  "action": "fold",        "amount": 0},
            {"seat": SB,  "action": "fold",        "amount": 0},
            {"seat": BB,  "action": "call",        "amount": 250},
            {"seat": BB,  "action": "raise",       "amount": 300},
            {"seat": UTG, "action": "fold",        "amount": 0},
            {"seat": ME,  "action": "call",        "amount": 300},
            {"seat": BB,  "action": "check",       "amount": 0},
            {"seat": ME,  "action": "raise",       "amount": 1287},
            {"seat": BB,  "action": "all_in",      "amount": 10128},
        ],
    }


state = build_turn_state()
ME, BB = 1, 4

# === Compare original vs patched ===
print("=== ORIGINAL (buggy) _preflop_action_log ===")
pf_orig = bot._preflop_action_log(state)
print(f"  returns {len(pf_orig)} entries (whole log has {len(state['action_log'])})")
n_postflop_raises_orig = bot.count_postflop_raises(state, BB)
n_aggressors_orig = bot.count_aggressors(state)
print(f"  count_postflop_raises(BB)  = {n_postflop_raises_orig}")
print(f"  count_aggressors           = {n_aggressors_orig}")

print()
print("=== PATCHED _preflop_action_log ===")
pf_patched = patched_preflop_action_log(state)
print(f"  returns {len(pf_patched)} entries (preflop should be 7)")

# Monkey-patch and re-test
bot._preflop_action_log = patched_preflop_action_log
n_postflop_raises_new = bot.count_postflop_raises(state, BB)
n_aggressors_new = bot.count_aggressors(state)
print(f"  count_postflop_raises(BB)  = {n_postflop_raises_new}   (expected: 2)")
print(f"  count_aggressors           = {n_aggressors_new}   (expected: 1, deepseek pf raiser)")

# === Re-run the equity estimate with patched version ===
print()
print("=== EQUITY ESTIMATE: ORIGINAL vs PATCHED ===")
# (the bot module still has the patched _preflop_action_log)
v_range_patched = bot.aggressor_likely_range(state, BB)
nz = {k: v for k, v in v_range_patched.items() if v > 0}
print(f"  Patched aggressor_likely_range size  = {len(nz)} entries")
print(f"  Sample: {dict(list(nz.items())[:10])}")
eq_patched = bot.equity_vs_range(
    state["your_cards"], state["community_cards"],
    v_range_patched, n_sims=400, rng=random.Random(42)
)
print(f"  Patched eq(KK22 vs range)            = {eq_patched:.4f} ({eq_patched*100:.1f}%)")

# Restore original and compare
spec.loader.exec_module(bot)
v_range_orig = bot.aggressor_likely_range(state, BB)
eq_orig = bot.equity_vs_range(
    state["your_cards"], state["community_cards"],
    v_range_orig, n_sims=400, rng=random.Random(42)
)
print(f"  Original eq(KK22 vs range)           = {eq_orig:.4f} ({eq_orig*100:.1f}%)")

print()
print("=== DECISION CHANGE ===")
# pot_odds + buffers (same as before) require ~54%
print(f"  Required equity (pot_odds + buffers) ≈ 54.4%")
print(f"  Original equity {eq_orig*100:.1f}% > 54.4% → CALLS (the actual bust)")
print(f"  Patched equity  {eq_patched*100:.1f}% {'>' if eq_patched > 0.544 else '<'} 54.4% → "
      f"{'CALLS' if eq_patched > 0.544 else 'FOLDS'}")
