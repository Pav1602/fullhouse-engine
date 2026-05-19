import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util
import eval7
from engine.game import PokerEngine

def _load_bot(path: str):
    spec = importlib.util.spec_from_file_location("bot_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def run_diagnostic():
    g = PokerEngine(
        hand_id="h20",
        bot_ids=["human", "skantbot7"],
        starting_stacks={"human": 17236, "skantbot7": 2764},
        dealer_seat=0,  # human is SB, seat 0
        seed=42,
    )
    state = g.start_hand()
    
    # Hole cards: bot = ["Ts","Jh"], opp = ["Kd","Qh"]
    g.players[0].hole_cards = [eval7.Card("Kd"), eval7.Card("Qh")]
    g.players[1].hole_cards = [eval7.Card("Ts"), eval7.Card("Jh")]
    
    actions = [
        {"seat": 0, "action": "raise", "amount": 200},
        {"seat": 1, "action": "call"},
        {"street": "flop", "cards": ["8h", "2c", "Jd"]},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 372},
        {"seat": 0, "action": "call"},
        {"street": "turn", "cards": ["8h", "2c", "Jd", "2h"]},
        {"seat": 0, "action": "check"},
        {"seat": 1, "action": "raise", "amount": 1066},
        {"seat": 0, "action": "all_in"}
    ]
    
    for a in actions:
        if "street" in a:
            cards = [eval7.Card(c) for c in a["cards"]]
            g.community_cards = cards
            state["community_cards"] = a["cards"]
            continue
        seat = a["seat"]
        state = g.apply_action(seat, a)
        
    mod = _load_bot("bots/skantbot7.4/bot.py")
    
    captured = {}
    
    orig_eq = mod.equity_vs_range
    def wrap_eq(hole, board, villain_range, n_sims=300):
        r = orig_eq(hole, board, villain_range, n_sims)
        captured.setdefault("eq", []).append({
            "range_size": sum(villain_range.values()),
            "equity": r,
            "n_sims": n_sims,
            "top_combos": sorted([(k,v) for k,v in villain_range.items() if v>0],
                                 key=lambda x: -x[1])[:10],
        })
        return r
    mod.equity_vs_range = wrap_eq
    
    orig_ar = mod.aggressor_likely_range
    def wrap_ar(state, agg_seat):
        r = orig_ar(state, agg_seat)
        captured.setdefault("range_calls", []).append({
            "size": sum(r.values()),
            "top": sorted([(k,v) for k,v in r.items() if v>0], key=lambda x: -x[1])[:10],
        })
        return r
    mod.aggressor_likely_range = wrap_ar
    
    decision = mod.decide(state)
    
    print(f"1. Decision: {decision}")
    
    agg = mod.count_aggressors(state)
    print(f"2. count_aggressors: {agg}")
    
    pf_raises = mod.count_postflop_raises(state, 0)
    print(f"3. count_postflop_raises (seat 0): {pf_raises}")
    
    print(f"4. aggressor_likely_range: {captured.get('range_calls', [])}")
    print(f"5. equity_vs_range: {captured.get('eq', [])}")
    
    pot = state["pot"]
    owed = state["amount_owed"]
    stack = state["your_stack"]
    pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 1.0
    # Note: Stage 3 (effective_owed) is NOT in 7.4. So risk_pct uses uncapped owed.
    risk_pct = mod.stack_risked_pct(state, owed)
    variance_term = mod.CONFIG.variance_c * (risk_pct ** 2)
    cold_caution = mod.CONFIG.cold_start_caution if mod.any_active_unknown(state, mod.CONFIG) else 0.0
    required_eq = pot_odds + mod.CONFIG.pot_odds_buffer_normal + variance_term + cold_caution
    
    print(f"6. Manual Calc:")
    print(f"   pot: {pot}")
    print(f"   owed: {owed}")
    print(f"   your_stack: {stack}")
    print(f"   risk_pct: {risk_pct:.4f}")
    print(f"   pot_odds: {pot_odds:.4f}")
    print(f"   variance_term: {variance_term:.4f}")
    print(f"   cold_caution: {cold_caution:.4f}")
    print(f"   required_eq (normal branch): {required_eq:.4f}")

if __name__ == "__main__":
    run_diagnostic()
