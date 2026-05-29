"""V81 §5.4 — Paper-hand verification for skantbot8 #1 (bet-sizing signal).

For each scenario, pre-populates OPPONENTS["opp0"] with a synthetic profile
(N hands, M postflop bets with controlled mean bet/pot ratio), then calls
aggressor_likely_range on a state with the opp's bet sized at a tested
multiplier × mean. Verifies the signal fires (strength → strong → narrower
range) exactly when expected.

Acceptance: 5/5 scenarios match the prediction. If any miss, the
implementation diverges from the design — fix before continuing.

Usage:
    python _paper_hands_skb8_step1.py bots/skantbot8/bot.py
"""
import sys, importlib.util
sys.path.insert(0, ".")

BOT_PATH = sys.argv[1] if len(sys.argv) > 1 else "bots/skantbot8/bot.py"


def load_bot(path):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def players_6max(skant_seat=2):
    return [
        {"seat": s, "bot_id": ("skant" if s == skant_seat else f"opp{s}"),
         "stack": 10000, "bet_this_street": 0, "is_folded": False,
         "is_all_in": False, "total_invested": 0}
        for s in range(6)
    ]


def state_flop_btn_bet(opp_seat, opp_bet_to, pot_after):
    """6-max BTN opens, BB calls, flop K72r, BB checks, BTN bets `opp_bet_to`."""
    return {
        "type": "action_request",
        "seat_to_act": 2,
        "community_cards": ["Ks", "7d", "2c"],
        "pot": pot_after,
        "players": players_6max(),
        "action_log": [
            {"seat": 1, "action": "small_blind", "amount": 50},
            {"seat": 2, "action": "big_blind",   "amount": 100},
            {"seat": 3, "action": "fold",        "amount": 0},
            {"seat": 4, "action": "fold",        "amount": 0},
            {"seat": 5, "action": "fold",        "amount": 0},
            {"seat": 0, "action": "raise",       "amount": 300},
            {"seat": 1, "action": "fold",        "amount": 0},
            {"seat": 2, "action": "call",        "amount": 200},
            {"seat": 2, "action": "check",       "amount": 0},
            {"seat": 0, "action": "raise",       "amount": opp_bet_to},
        ],
    }


def install_profile(bot, opp_id, hands_observed, mean_bpp, n_bets):
    """Reset OPPONENTS, install a synthetic profile."""
    bot.OPPONENTS.clear()
    prof = bot.OPPONENTS[opp_id]
    prof.hands_observed = hands_observed
    prof.bet_size_pcts = [mean_bpp] * n_bets


def run(bot, label, scenario, prof_args, opp_bet_to, pot_after, expect_strong):
    install_profile(bot, **prof_args)
    # Patch the bot_id for seat 0 (the aggressor) to match opp_id
    st = scenario(0, opp_bet_to=opp_bet_to, pot_after=pot_after)
    for p in st["players"]:
        if p["seat"] == 0:
            p["bot_id"] = prof_args["opp_id"]
    rng = bot.aggressor_likely_range(st, agg_seat=0)
    size = len(rng) if rng else 0
    sum_freq = round(sum(rng.values()), 2) if rng else 0.0
    # "strong" tier produces ~13-15 hands (premiums only); "medium" ~25 hands.
    actual_strong = size <= 20  # heuristic threshold
    match = (actual_strong == expect_strong)
    flag = "✓" if match else "✗"
    print(f"  {flag} {label:<48}  size={size:>3}  sum={sum_freq:>5}  "
          f"expect_strong={expect_strong}  actual_strong={actual_strong}")
    return match


def main():
    bot = load_bot(BOT_PATH)
    print(f"Bot: {BOT_PATH}\n")
    print("Scenarios — synthetic opp 'opp0' on dry K72r flop, BTN bet sizing varied.\n")
    results = []

    # Common signal-eligible profile: 50 hands observed, 10 bets, mean bet/pot = 0.50
    prof_low = {"opp_id": "opp0", "hands_observed": 50,
                "mean_bpp": 0.50, "n_bets": 10}

    # Scenario A: opp bet 0.9 of pot — bet/mean ratio = 0.9/0.5 = 1.8 ≥ 1.5 → FIRE
    # Pot before bet = 600 (BTN open 300 + BB call 300 actually — let's compute).
    # Action log puts pot at 600 going into postflop (300+300 from preflop).
    # BTN bets `opp_bet_to`, state["pot"] = pot_before_bet + amount.
    # For ratio 0.9: amount / pot_after = 0.9 → amount = 0.9 * pot_after.
    # With pot_before_bet=600 and amount=A: pot_after = 600+A. amount/pot_after = 0.9
    # → A = 0.9*(600+A) → 0.1A = 540 → A=5400. Pot_after = 6000.
    results.append(run(
        bot, "A: opp bet 90% pot (1.8× mean) — should fire",
        state_flop_btn_bet, prof_low,
        opp_bet_to=5400, pot_after=6000, expect_strong=True,
    ))

    # Scenario B: opp bet 30% pot (0.6× mean) — should NOT fire
    # ratio amount/pot_after = 0.3, amount = 0.3*(600+A), A = 257
    results.append(run(
        bot, "B: opp bet 30% pot (0.6× mean) — no fire",
        state_flop_btn_bet, prof_low,
        opp_bet_to=257, pot_after=857, expect_strong=False,
    ))

    # Scenario C: signal eligibility — under MIN_OBS (15 hands) → no fire even if big
    prof_under_obs = {"opp_id": "opp0", "hands_observed": 15,
                      "mean_bpp": 0.50, "n_bets": 10}
    results.append(run(
        bot, "C: <30 hands observed → guarded, no fire",
        state_flop_btn_bet, prof_under_obs,
        opp_bet_to=5400, pot_after=6000, expect_strong=False,
    ))

    # Scenario D: empty bet_size_pcts → no fire even with 50 hands
    prof_empty_bets = {"opp_id": "opp0", "hands_observed": 50,
                       "mean_bpp": 0.66, "n_bets": 0}
    results.append(run(
        bot, "D: 0 bets observed → guarded, no fire (cold-start)",
        state_flop_btn_bet, prof_empty_bets,
        opp_bet_to=5400, pot_after=6000, expect_strong=False,
    ))

    # Scenario E: min_raiser-like profile (mean small ~0.15), normal small bet
    # mean=0.15, opp bet at 0.20 of pot → ratio 1.33 < 1.5 → NO FIRE.
    # ratio amount/pot_after = 0.20 → A = 0.20*(600+A) → 0.8A=120 → A=150. pot=750
    prof_min_raiser = {"opp_id": "opp0", "hands_observed": 50,
                       "mean_bpp": 0.15, "n_bets": 30}
    results.append(run(
        bot, "E: min_raiser-style, small bet — must NOT fire",
        state_flop_btn_bet, prof_min_raiser,
        opp_bet_to=150, pot_after=750, expect_strong=False,
    ))

    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} paper hands match prediction.")
    if n_pass != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
