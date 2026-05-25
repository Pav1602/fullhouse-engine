"""Trace skantbot7.9's turn-call decision in hand_h0027 (the K2o bust).

Methodology per memory/feedback_trace_table_before_changes.md +
memory/feedback_verify_runtime_values.md: construct the EXACT game state the
bot saw at decision time, run the bot's own functions, log every intermediate
variable. No speculation about 'should be' values."""

import sys, random
sys.path.insert(0, ".")
sys.path.insert(0, "bots/skantbot7.9")

import importlib.util
spec = importlib.util.spec_from_file_location("skb79", "bots/skantbot7.9/bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def build_turn_state():
    """Construct the state skantbot saw when it had to call human's all-in on turn.

    Hand 27 action log up to that point:
      PREFLOP: chatgpt-2 SB 50; human BB 100; deepseek-10 raise 250;
               skantbot7.9 call 250; chatgpt-7 fold; chatgpt-2 fold; human call 150
      FLOP [2c Jh Kc]: human raise 300; deepseek-10 fold; skantbot7.9 call 300
      TURN [2c Jh Kc 7c]: human check; skantbot7.9 raise 1287; human all_in 10128
    """
    # Seat assignments (preflop action order: UTG first):
    #   seat 0: deepseek-10 (UTG)
    #   seat 1: skantbot7.9
    #   seat 2: chatgpt-7
    #   seat 3: chatgpt-2 (SB)
    #   seat 4: human (BB)
    # 5-handed table.
    SB, BB, UTG, ME, CO = 3, 4, 0, 1, 2

    # Pot accounting at moment of decision (human just shoved 10128, skantbot to act):
    # Preflop: chatgpt-2(50 SB forfeit-ish) + human(100→250) + deepseek(250) + skantbot(250) = 800
    # Flop:    human(300) + skantbot(300) = +600 → pot 1400
    # Turn:    skantbot(1287) + human(10128) = +11415 → pot 12815 (uncallable excess to be refunded)
    POT_AT_DECISION = 1400 + 1287 + 10128

    # Skantbot's stack at moment of decision = call amount in log
    # (engine logs "call 8498" = chips contributed = stack remaining)
    STACK = 8498
    OWED  = 10128 - 1287   # = 8841 (more than stack → all-in for less)

    state = {
        "type": "action_request",
        "hand_id": "human_vs_skantbot7.9_6max_h0027",
        "street": "turn",
        "seat_to_act": ME,
        "pot": POT_AT_DECISION,
        "community_cards": ["2c", "Jh", "Kc", "7c"],
        "current_bet": 10128,
        "min_raise_to": 10128 + 8841,   # not used in this path
        "amount_owed": OWED,
        "can_check": False,
        "your_cards": ["Kh", "2s"],
        "your_stack": STACK,
        "your_bet_this_street": 1287,
        "players": [
            {"seat": UTG, "bot_id": "deepseek-10", "is_folded": True,  "is_all_in": False, "stack": 0},
            {"seat": ME,  "bot_id": "skantbot7.9", "is_folded": False, "is_all_in": False, "stack": STACK},
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
            # Flop
            {"seat": BB,  "action": "raise",       "amount": 300},
            {"seat": UTG, "action": "fold",        "amount": 0},
            {"seat": ME,  "action": "call",        "amount": 300},
            # Turn (up to but NOT including skantbot's pending decision)
            {"seat": BB,  "action": "check",       "amount": 0},
            {"seat": ME,  "action": "raise",       "amount": 1287},
            {"seat": BB,  "action": "all_in",      "amount": 10128},
        ],
    }
    return state, ME, BB


def trace(state, ME, BB):
    cfg = bot.CONFIG
    rng = random.Random(42)

    print("=" * 72)
    print(f"TURN DECISION TRACE — {state['hand_id']}")
    print("=" * 72)
    print(f"Hole:   {state['your_cards']}")
    print(f"Board:  {state['community_cards']}")
    print(f"Pot:    {state['pot']}   Stack: {state['your_stack']}   Owed: {state['amount_owed']}")
    print()

    # === Position ===
    position = bot.get_position_label(state)
    print(f"position                       = {position}")
    in_position = position in ("CO", "BTN")
    print(f"in_position                    = {in_position}")

    # === Aggressor identification ===
    agg_seat = bot.find_aggressor_seat(state)
    print(f"find_aggressor_seat(state)     = {agg_seat}   (BB seat={BB}, expected=BB)")
    agg_id = next((p["bot_id"] for p in state["players"] if p["seat"] == agg_seat), None)
    print(f"aggressor bot_id               = {agg_id}")

    n_pf_raises = bot.count_postflop_raises(state, agg_seat)
    print(f"count_postflop_raises          = {n_pf_raises}")
    last_is_allin = bot._aggressor_last_action_is_allin(state, agg_seat)
    print(f"_aggressor_last_action_is_allin = {last_is_allin}")

    n_aggressors = bot.count_aggressors(state)
    print(f"count_aggressors               = {n_aggressors}")
    agg_pos = bot.get_opp_position(state, agg_seat)
    print(f"aggressor_position             = {agg_pos}")

    # === Board texture ===
    tex_label = bot.board_texture(state["community_cards"])
    tex_feat  = bot.board_texture_features(state["community_cards"])
    print(f"board_texture                  = {tex_label}")
    print(f"board_texture_features         = {tex_feat}")
    # 4-flush check (4 cards same suit on board)
    suits = [c[1] for c in state["community_cards"]]
    max_suit_count = max(suits.count(s) for s in set(suits))
    print(f"max same-suit count on board   = {max_suit_count}   (4 = flush completed)")

    # === Range estimation ===
    v_range = bot.aggressor_likely_range(state, agg_seat)
    nonzero = {k: v for k, v in v_range.items() if v > 0}
    print(f"aggressor_likely_range size    = {len(nonzero)} non-zero entries")
    print(f"aggressor_likely_range sample  = {dict(list(nonzero.items())[:10])}")

    # === Equity ===
    n_sims = cfg.mc_sims_turn
    eq = bot.equity_vs_range(state["your_cards"], state["community_cards"],
                             v_range, n_sims=n_sims, rng=rng)
    print(f"mc_sims_turn                   = {n_sims}")
    print(f"equity_vs_range(KK22 vs range) = {eq:.4f}   ({eq*100:.1f}%)")

    # === Pot odds and required equity ===
    owed = state["amount_owed"]
    stack = state["your_stack"]
    pot = state["pot"]
    effective_owed = min(owed, stack)
    callable_pot   = pot - (owed - effective_owed)
    pot_odds = effective_owed / (callable_pot + effective_owed) if (callable_pot + effective_owed) > 0 else 1.0
    risk_pct = bot.stack_risked_pct(state, effective_owed)
    variance_term = cfg.variance_c * (risk_pct ** 2)
    required_eq = pot_odds + cfg.pot_odds_buffer_normal + variance_term  # cold_caution assumed 0

    print()
    print(f"effective_owed                 = {effective_owed}")
    print(f"callable_pot                   = {callable_pot}")
    print(f"pot_odds                       = {pot_odds:.4f}   ({pot_odds*100:.1f}%)")
    print(f"risk_pct (stack at risk)       = {risk_pct:.4f}   ({risk_pct*100:.1f}%)")
    print(f"variance_c (cfg)               = {cfg.variance_c}")
    print(f"variance_term                  = {variance_term:.4f}")
    print(f"pot_odds_buffer_normal         = {cfg.pot_odds_buffer_normal}")
    print(f"required_eq for call           = {required_eq:.4f}   ({required_eq*100:.1f}%)")

    # === Decision branches ===
    print()
    print("--- DECISION BRANCH ANALYSIS ---")
    print(f"branch 1: eq >= equity_raise_threshold ({cfg.equity_raise_threshold})?    {eq >= cfg.equity_raise_threshold}")
    print(f"branch 2: eq >= required_eq ({required_eq:.4f})?                          {eq >= required_eq}")

    # SPR commitment
    import math
    spr = stack / max(callable_pot, 1)
    commitment_factor = 1.0 / (1.0 + math.exp((spr - cfg.spr_commit_threshold) / cfg.spr_smoothness))
    commit_thresh_3 = cfg.equity_value_bet - cfg.k_commit * commitment_factor
    print(f"branch 3 (SPR commit):")
    print(f"  spr                          = {spr:.4f}")
    print(f"  spr_commit_threshold (cfg)   = {cfg.spr_commit_threshold}")
    print(f"  commitment_factor            = {commitment_factor:.4f}")
    print(f"  k_commit (cfg)               = {cfg.k_commit}")
    print(f"  threshold = eq_value_bet - k_commit*cf = {commit_thresh_3:.4f}")
    print(f"  variance_term <= 0?          = {variance_term <= 0}")
    print(f"  branch 3 fires?              = {eq >= commit_thresh_3 and variance_term <= 0}")

    # Final actual decision
    print()
    print("--- ACTUAL BOT DECISION ---")
    action = bot.decide_postflop(state, position, cfg, random.Random(42))
    print(f"decide_postflop returned:      {action}")


if __name__ == "__main__":
    state, ME, BB = build_turn_state()
    trace(state, ME, BB)
