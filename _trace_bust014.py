"""Trace skantbot 7.10's river call decision in bust_014_h0142.

Per advisor: determine whether the late-street hero-call leak is:
  (1) commitment override clause fires with low equity -> STRUCTURAL
  (2) aggressor_likely_range didn't narrow on multi-raise line -> STRUCTURAL
  (3) low pot_odds (most stack already in) makes required_eq low -> PARAMETER
"""
import sys, random, importlib.util
sys.path.insert(0, ".")

spec = importlib.util.spec_from_file_location("bot", "bots/skantbot7.11/bot.py")
bot = importlib.util.module_from_spec(spec); spec.loader.exec_module(bot)


# Reconstruct state at skant's river-call decision.
#
# Action log up to that point:
#   PREFLOP: s2 SB 50; s0 BB 100; s1 call 100; s2 call 50; (no raises — free flop)
#   FLOP [Td 3c 5c]: s0 check; s2 check; s0 raise 271; s1 raise 1142;
#                    s2 fold; s0 call 871
#   TURN [Td 3c 5c 7s]: s0 raise 2338; s1 raise 9844; s0 call 7506
#   RIVER [Td 3c 5c 7s Kh]: s0 check; s1 raise 20044; <skant_decision>
#
# Skant is s0 (BB, then donk-leads flop and turn, then calls jam on river).
# Opp aggressor is s1 (chatgpt-2). s2 folded on flop.
#
# Stack reconstruction:
# - Final loss for skant = 16850 (recorded in bust survey).
# - Across the hand skant put in: 100 + 1142 + 9844 + (river all-in for less)
# - 100 + 1142 + 9844 = 11086 in first 3 streets.
# - Therefore skant's remaining stack at start of river action = 16850 - 11086 = 5764.
# - skant called 20044 attempted (capped to 5764 stack = all-in for less).
# - For the decide_postflop call: state["your_stack"] = 5764, owed = 20044.
#
# Pot at the call decision (after chatgpt-2 raise, before skant call):
# - Preflop:  s2 50 + s0 100 + s1 100 + s2 50 = 300
# - Flop:     skant 1142 + chatgpt-2 1142 = 2284  (s2 folded, no flop chips)
# - Turn:     skant 9844 + chatgpt-2 9844 = 19688
# - River so far: chatgpt-2 20044
# - Total pot = 300 + 2284 + 19688 + 20044 = 42316


SKANT_SEAT = 0
OPP_SEAT = 1
DEAD_SEAT = 2

state = {
    "type": "action_request",
    "hand_id": "bust_survey_014_h0142",
    "street": "river",
    "seat_to_act": SKANT_SEAT,
    "pot": 42316,
    "community_cards": ["Td", "3c", "5c", "7s", "Kh"],
    "current_bet": 20044,
    "min_raise_to": 20044 * 2,  # not used in fold/call path
    "amount_owed": 20044,        # = current_bet - bet_this_street (0 at river start)
    "can_check": False,
    "your_cards": ["Ts", "Ac"],   # skant's revealed cards
    "your_stack": 5764,
    "your_bet_this_street": 0,
    "players": [
        {"seat": SKANT_SEAT, "bot_id": "skantbot7.10", "is_folded": False, "is_all_in": False, "stack": 5764},
        {"seat": OPP_SEAT,   "bot_id": "chatgpt-2",    "is_folded": False, "is_all_in": True,  "stack": 0},
        {"seat": DEAD_SEAT,  "bot_id": "mathematician","is_folded": True,  "is_all_in": False, "stack": 9700},
    ],
    "action_log": [
        # Preflop (no raises)
        {"seat": DEAD_SEAT, "action": "small_blind", "amount": 50},
        {"seat": SKANT_SEAT,"action": "big_blind",   "amount": 100},
        {"seat": OPP_SEAT,  "action": "call",        "amount": 100},
        {"seat": DEAD_SEAT, "action": "call",        "amount": 50},
        {"seat": SKANT_SEAT,"action": "check",       "amount": 0},
        {"seat": DEAD_SEAT, "action": "check",       "amount": 0},
        # Flop
        {"seat": SKANT_SEAT,"action": "raise",       "amount": 271},
        {"seat": OPP_SEAT,  "action": "raise",       "amount": 1142},
        {"seat": DEAD_SEAT, "action": "fold",        "amount": 0},
        {"seat": SKANT_SEAT,"action": "call",        "amount": 871},
        # Turn
        {"seat": SKANT_SEAT,"action": "raise",       "amount": 2338},
        {"seat": OPP_SEAT,  "action": "raise",       "amount": 9844},
        {"seat": SKANT_SEAT,"action": "call",        "amount": 7506},
        # River — up to skant's pending decision
        {"seat": SKANT_SEAT,"action": "check",       "amount": 0},
        {"seat": OPP_SEAT,  "action": "raise",       "amount": 20044},
    ],
}


def inject_opp_profile(bot_mod, opp_id, fb=100, rwf=50, vpip=0.30, pfr=0.20, agg=2.0, wtsd=0.35, hands=142):
    """Inject a realistic opponent profile representing accumulated stats over the match.

    The Phase 2a scaling in aggressor_likely_range uses:
      reraise_freq = (rwf + 3) / (fb + 20)
      excess = max(0, reraise_freq - 0.15)
      w = max(0, 1 - excess / 0.85)
    Higher rwf -> lower w -> more weight on (wide) base_range -> higher equity estimate."""
    prof = bot_mod.BehaviouralProfile()
    prof.hands_observed = hands
    prof.faced_bet_postflop = fb
    prof.raised_when_faced_postflop = rwf
    # Stub other fields that show up in stat() lookups
    prof.vpip_count = int(hands * vpip)
    prof.pfr_count = int(hands * pfr)
    prof.went_to_showdown = int(hands * wtsd)
    prof.bets_made_total = max(1, int(fb * 0.5))
    prof.calls_made_total = max(1, int(fb * 0.25))
    bot_mod.OPPONENTS[opp_id] = prof


def trace(opp_rwf=None):
    cfg = bot.CONFIG
    rng = random.Random(42)
    if opp_rwf is not None:
        inject_opp_profile(bot, "chatgpt-2", fb=100, rwf=opp_rwf)
        print(f"[injected chatgpt-2 profile: fb=100 rwf={opp_rwf} -> reraise_freq={(opp_rwf+3)/120:.3f}]")

    print("=" * 72)
    print("BUST_014_h0142 — river call decision trace (skantbot7.10)")
    print("=" * 72)
    print(f"Hole:   {state['your_cards']}   Board: {state['community_cards']}")
    print(f"Pot:    {state['pot']}   Stack: {state['your_stack']}   Owed: {state['amount_owed']}")
    print()

    position = bot.get_position_label(state)
    print(f"position                       = {position}")
    in_position = position in ("CO", "BTN")
    print(f"in_position                    = {in_position}")

    agg_seat = bot.find_aggressor_seat(state)
    print(f"find_aggressor_seat            = {agg_seat}   (opp/chatgpt-2 expected)")

    agg_pos = bot.get_opp_position(state, agg_seat) if agg_seat is not None else None
    print(f"aggressor_position             = {agg_pos}")

    last_is_allin = bot._aggressor_last_action_is_allin(state, agg_seat)
    print(f"_aggressor_last_action_is_allin = {last_is_allin}")

    n_pf_raises = bot.count_postflop_raises(state, agg_seat)
    print(f"count_postflop_raises          = {n_pf_raises}   (expected 3: flop+turn+river)")

    n_aggressors = bot.count_aggressors(state)
    print(f"count_aggressors               = {n_aggressors}   (preflop only; expected 0)")

    tex = bot.board_texture(state["community_cards"])
    print(f"board_texture                  = {tex}")

    # Range model
    v_range = bot.aggressor_likely_range(state, agg_seat)
    nz = {k: v for k, v in v_range.items() if v > 0}
    print(f"aggressor_likely_range size    = {len(nz)} non-zero entries")
    print(f"  sample (first 15)            = {dict(list(nz.items())[:15])}")

    n_sims = cfg.mc_sims_river
    eq = bot.equity_vs_range(state["your_cards"], state["community_cards"],
                             v_range, n_sims=n_sims, rng=rng)
    print(f"mc_sims_river                  = {n_sims}")
    print(f"equity_vs_range (TT-pair vs r) = {eq:.4f}  ({eq*100:.1f}%)")

    # Pot odds, required_eq
    owed = state["amount_owed"]; stack = state["your_stack"]; pot = state["pot"]
    eff = min(owed, stack)
    callable_pot = pot - (owed - eff)
    pot_odds = eff / (callable_pot + eff) if (callable_pot + eff) > 0 else 1.0
    risk_pct = bot.stack_risked_pct(state, eff)
    variance_term = cfg.variance_c * (risk_pct ** 2)
    cold_caution = cfg.cold_start_caution if bot.any_active_unknown(state, cfg) else 0.0
    required_eq = pot_odds + cfg.pot_odds_buffer_normal + variance_term + cold_caution

    print()
    print(f"effective_owed                 = {eff}")
    print(f"callable_pot                   = {callable_pot}   (excludes opp's uncallable excess)")
    print(f"pot_odds                       = {pot_odds:.4f}  ({pot_odds*100:.1f}%)")
    print(f"risk_pct                       = {risk_pct:.4f}")
    print(f"variance_c                     = {cfg.variance_c}")
    print(f"variance_term                  = {variance_term:.4f}")
    print(f"pot_odds_buffer_normal         = {cfg.pot_odds_buffer_normal}")
    print(f"cold_caution_call              = {cold_caution}")
    print(f"required_eq for call           = {required_eq:.4f}  ({required_eq*100:.1f}%)")

    # SPR commitment branch (the structural override)
    import math
    spr = stack / max(callable_pot, 1)
    commit_factor = 1.0 / (1.0 + math.exp((spr - cfg.spr_commit_threshold) / cfg.spr_smoothness))
    commit_thresh = cfg.equity_value_bet - cfg.k_commit * commit_factor

    print()
    print("--- DECISION BRANCH EVALUATION ---")
    print(f"branch 1  eq >= equity_raise_threshold ({cfg.equity_raise_threshold:.4f})?")
    print(f"          {eq:.4f} >= {cfg.equity_raise_threshold:.4f}: {eq >= cfg.equity_raise_threshold}")
    print(f"branch 2  eq >= required_eq?")
    print(f"          {eq:.4f} >= {required_eq:.4f}: {eq >= required_eq}")
    print(f"branch 3  SPR commitment override")
    print(f"          spr                    = {spr:.4f}")
    print(f"          spr_commit_threshold   = {cfg.spr_commit_threshold:.4f}")
    print(f"          spr_smoothness         = {cfg.spr_smoothness:.4f}")
    print(f"          commitment_factor      = {commit_factor:.4f}")
    print(f"          k_commit               = {cfg.k_commit:.4f}")
    print(f"          equity_value_bet       = {cfg.equity_value_bet:.4f}")
    print(f"          threshold = eq_v_bet - k_commit*cf = {commit_thresh:.4f}")
    print(f"          variance_term <= 0?    = {variance_term <= 0}")
    print(f"          BRANCH 3 FIRES?        = {eq >= commit_thresh and variance_term <= 0}")

    # Branch 4 (final): tightened call vs aggression
    call_thresh = cfg.equity_call_threshold
    # Standing modifier (Phase 7) — relies on global our_match_delta
    standing_modifier = math.tanh(cfg.k_standing * getattr(bot, "our_match_delta", 0) / bot.INITIAL_STACK)
    call_thresh_modifier = 1.0 - cfg.standing_alpha * standing_modifier
    call_thresh *= call_thresh_modifier
    branch4_check = (eq >= (call_thresh - cfg.k_commit * commit_factor) and
                     owed <= pot * cfg.pot_odds_buffer_marginal and
                     variance_term <= 0)
    print(f"branch 4  call_thresh (modified) = {call_thresh:.4f}")
    print(f"          owed <= pot * marg_buf  = {owed <= pot * cfg.pot_odds_buffer_marginal} "
          f"({owed} <= {pot * cfg.pot_odds_buffer_marginal:.0f})")
    print(f"          BRANCH 4 FIRES?         = {branch4_check}")

    # Actual decision
    print()
    print("--- ACTUAL BOT DECISION ---")
    action = bot.decide_postflop(state, position, cfg, random.Random(42))
    print(f"decide_postflop returns:       {action}")

    # Diagnose
    print()
    print("--- DIAGNOSIS ---")
    if action.get("action") == "call":
        if eq >= cfg.equity_raise_threshold:
            verdict = "branch 1 (equity high enough to raise/call); equity model BROKEN"
        elif eq >= required_eq:
            verdict = "branch 2 (required_eq met); calls due to LOW pot_odds — PARAMETER (V80)"
        elif eq >= commit_thresh and variance_term <= 0:
            verdict = "branch 3 (SPR commitment override fired); STRUCTURAL — V80 will not close"
        elif branch4_check:
            verdict = "branch 4 (call_thresh override); PARAMETER (V80)"
        else:
            verdict = "UNKNOWN call path — investigate"
        print(f"  --> {verdict}")
    else:
        print(f"  decision was {action['action']}; current bot.py would NOT make this bust")


if __name__ == "__main__":
    import sys
    rwfs = [None, 10, 25, 50, 70, 90]
    for r in rwfs:
        # Reset OPPONENTS each iteration
        bot.OPPONENTS.clear()
        print("\n" + "#" * 72)
        print(f"# SWEEP: opp_rwf = {r}  (None = no profile)")
        print("#" * 72)
        trace(opp_rwf=r)
