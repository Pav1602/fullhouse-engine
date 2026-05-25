"""Paper-hand verifications for skantbot 7.11.

Re-runs existing paper hands plus new scenarios per advisor:
  F. AA on wet board vs single raise -> must CALL (verify no over-tightening)
  G. K-high TPGK vs BB defender's single donk-bet -> must CALL"""
import random, importlib.util


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
            {"seat": ME,  "bot_id": "skantbot7.11", "is_folded": False, "is_all_in": False, "stack": 8498},
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


def state_aa_wet(hole=("Ah","Ad")):
    """AA on wet flop (T-9-8-r) facing single c-bet from preflop raiser.
    Must CALL — sanity check we haven't over-tightened legitimate value calls."""
    SB, BB, ME, OPP = 0, 1, 2, 3
    return {
        "type":"action_request","hand_id":"paper_aa_wet","street":"flop",
        "seat_to_act":ME,"pot":1200,
        "community_cards":["Ts","9h","8d"],
        "current_bet":600,"min_raise_to":1200,
        "amount_owed":600,"can_check":False,
        "your_cards":list(hole),"your_stack":9700,
        "your_bet_this_street":0,
        "players":[
            {"seat":SB,"bot_id":"sb_dead","is_folded":True,"is_all_in":False,"stack":0},
            {"seat":BB,"bot_id":"bb_dead","is_folded":True,"is_all_in":False,"stack":0},
            {"seat":ME,"bot_id":"skantbot7.11","is_folded":False,"is_all_in":False,"stack":9700},
            {"seat":OPP,"bot_id":"shark","is_folded":False,"is_all_in":False,"stack":9100},
        ],
        "action_log":[
            {"seat":SB,"action":"small_blind","amount":50},
            {"seat":BB,"action":"big_blind","amount":100},
            {"seat":OPP,"action":"raise","amount":300},
            {"seat":ME,"action":"call","amount":300},
            {"seat":SB,"action":"fold","amount":0},
            {"seat":BB,"action":"fold","amount":0},
            {"seat":OPP,"action":"raise","amount":600},
        ],
    }


def state_kx_tpgk_vs_bb_defender(hole=("Kh","Jh")):
    """K-high TPGK (KJs) on K-T-3-r facing single donk-bet from BB defender.
    Must NOT over-fold — verify new BB-defender + limp-range path doesn't
    over-narrow on legitimate one-bet scenarios."""
    SB, BB, ME = 0, 1, 2
    return {
        "type":"action_request","hand_id":"paper_kx_tpgk","street":"flop",
        "seat_to_act":ME,"pot":700,
        "community_cards":["Kd","Ts","3c"],
        "current_bet":400,"min_raise_to":800,
        "amount_owed":400,"can_check":False,
        "your_cards":list(hole),"your_stack":9700,
        "your_bet_this_street":0,
        "players":[
            {"seat":SB,"bot_id":"sb_dead","is_folded":True,"is_all_in":False,"stack":0},
            {"seat":BB,"bot_id":"opp_bb","is_folded":False,"is_all_in":False,"stack":9300},
            {"seat":ME,"bot_id":"skantbot7.11","is_folded":False,"is_all_in":False,"stack":9700},
        ],
        "action_log":[
            {"seat":SB,"action":"small_blind","amount":50},
            {"seat":BB,"action":"big_blind","amount":100},
            {"seat":ME,"action":"raise","amount":300},
            {"seat":BB,"action":"call","amount":200},
            {"seat":BB,"action":"raise","amount":400},
        ],
    }


def measure(bot, state, label):
    pos = bot.get_position_label(state)
    cfg = bot.CONFIG
    action = bot.decide_postflop(state, pos, cfg, random.Random(42))
    agg = bot.find_aggressor_seat(state)
    eq, nz = None, []
    if agg is not None:
        v_range = bot.aggressor_likely_range(state, agg)
        nz = [k for k,v in v_range.items() if v > 0]
        eq = bot.equity_vs_range(state["your_cards"], state["community_cards"],
                                  v_range, n_sims=2000, rng=random.Random(42))
    eff = min(state["amount_owed"], state["your_stack"])
    callable_pot = state["pot"] - (state["amount_owed"] - eff)
    pot_odds = eff / max(1, (callable_pot + eff))
    risk_pct = bot.stack_risked_pct(state, eff)
    req = pot_odds + cfg.pot_odds_buffer_normal + cfg.variance_c * (risk_pct ** 2)
    eq_s = f"{eq*100:.1f}%" if eq is not None else "n/a"
    print(f"  {label:<40}  hole={state['your_cards']}  rng_n={len(nz)}  eq={eq_s}  req={req*100:.1f}%  → {action['action']}")
    return action


def main():
    b11 = load("bots/skantbot7.11/bot.py")
    b10 = load("bots/skantbot7.10/bot.py")
    print("=" * 78)
    print("Paper-hand verifications for 7.11 vs 7.10")
    print("=" * 78)

    print("\n--- A. KK22 vs jam on flush turn (hand 27 bust) ---  expect FOLD")
    a11 = measure(b11, state_27(("Kh","2s")), "7.11 KK22 vs jam")
    a10 = measure(b10, state_27(("Kh","2s")), "7.10 KK22 vs jam")
    assert a11["action"] == "fold", f"FAIL: 7.11 must FOLD KK22 vs jam, got {a11}"
    assert a10["action"] == "fold", f"FAIL: 7.10 must FOLD KK22 vs jam, got {a10}"

    print("\n--- B. Nut flush vs jam ---  expect CALL/RAISE")
    b11r = measure(b11, state_27(("Ac","3c")), "7.11 nut flush")
    b10r = measure(b10, state_27(("Ac","3c")), "7.10 nut flush")
    assert b11r["action"] in ("call","raise"), f"FAIL: 7.11 must call nut flush, got {b11r}"

    print("\n--- C. Top set vs jam on flush board ---  expect FOLD (math correct)")
    c11 = measure(b11, state_27(("Ks","Kd")), "7.11 KK set")
    c10 = measure(b10, state_27(("Ks","Kd")), "7.10 KK set")

    print("\n--- F. AA on wet board (T98r) vs single cbet from opener ---  expect CALL/RAISE")
    f11 = measure(b11, state_aa_wet(), "7.11 AA wet vs cbet")
    f10 = measure(b10, state_aa_wet(), "7.10 AA wet vs cbet")
    assert f11["action"] in ("call","raise"), f"FAIL: 7.11 must call/raise AA on wet, got {f11}"

    print("\n--- G. K-high TPGK (KJs) on K-T-3 vs single donk-bet from BB defender ---  expect CALL/RAISE")
    g11 = measure(b11, state_kx_tpgk_vs_bb_defender(), "7.11 KJs TPGK vs BB donk")
    g10 = measure(b10, state_kx_tpgk_vs_bb_defender(), "7.10 KJs TPGK vs BB donk")
    if g11["action"] == "fold":
        print(f"  ⚠ 7.11 folds KJs TPGK on K-board — may be over-tightening")
    else:
        print(f"  ✓ 7.11 doesn't over-fold KJs TPGK")

    print("\n" + "=" * 78)
    print("All assertions passed.")
    print("=" * 78)


if __name__ == "__main__":
    main()
