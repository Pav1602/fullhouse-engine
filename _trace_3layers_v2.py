"""Layered trace v2: now that we've discovered the empty-subset fallback in
_narrow_range, the 'three issues' are actually:

  1. _preflop_action_log boundary bug (returns full log when folders leave
     partial bets behind) → wrong postflop-raise count → narrowing skipped.
  2. aggressor_likely_range has no path for BB-defender-as-aggressor → uses
     RFI fallback (wrong range entirely).
  3. _narrow_range collapses on defending ranges (premium subset empty) and
     is not board-aware for completing flushes/sets.

Each fix in isolation doesn't close hand 27 — they're entangled. This script
applies them progressively and reports equity at each step."""
import sys, random, importlib.util
sys.path.insert(0, ".")


def fresh_bot():
    spec = importlib.util.spec_from_file_location("skb79", "bots/skantbot7.9/bot.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def state_27():
    SB, BB, UTG, ME, CO = 3, 4, 0, 1, 2
    return {
        "type": "action_request", "hand_id": "h0027", "street": "turn",
        "seat_to_act": ME, "pot": 12815,
        "community_cards": ["2c", "Jh", "Kc", "7c"],
        "current_bet": 10128, "min_raise_to": 18969,
        "amount_owed": 8841, "can_check": False,
        "your_cards": ["Kh", "2s"], "your_stack": 8498,
        "your_bet_this_street": 1287,
        "players": [
            {"seat": UTG, "bot_id": "deepseek-10", "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": ME,  "bot_id": "skantbot7.9", "is_folded": False, "is_all_in": False, "stack": 8498},
            {"seat": CO,  "bot_id": "chatgpt-7",   "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": SB,  "bot_id": "chatgpt-2",   "is_folded": True, "is_all_in": False, "stack": 0},
            {"seat": BB,  "bot_id": "human",       "is_folded": False, "is_all_in": True, "stack": 0},
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


# === FIX 1: _preflop_action_log ===========================================
def fix1(bot_mod):
    def patched(state):
        log = state.get("action_log", [])
        pf, bets, folded = [], {}, set()
        saw_voluntary, in_pf = False, True
        for e in log:
            if not in_pf: break
            seat = e.get("seat"); action = e.get("action"); amt = e.get("amount", 0)
            pf.append(e)
            if action in ("small_blind", "big_blind"):
                bets[seat] = amt; continue
            if action == "fold":
                folded.add(seat); continue
            saw_voluntary = True
            if action in ("raise", "all_in"):
                bets[seat] = amt
            elif action == "call":
                bets[seat] = max(bets.values())
            active = [v for s, v in bets.items() if s not in folded]
            if saw_voluntary and len(active) >= 2 and all(v == active[0] for v in active):
                in_pf = False; break
        return pf
    bot_mod._preflop_action_log = patched


# === FIX 2: BB-defender base range =========================================
def fix2(bot_mod):
    _expand = bot_mod._expand_to_freq_dict
    THREEBET_CALL_FREQS = bot_mod.THREEBET_CALL_FREQS
    RFI_FREQS = bot_mod.RFI_FREQS

    orig = bot_mod.aggressor_likely_range
    def patched(state, agg_seat):
        agg_pos = bot_mod.get_opp_position(state, agg_seat)
        pf_log = bot_mod._preflop_action_log(state)

        # Detect "blind-defender as aggressor"
        opener_seat = None
        agg_pf_action = None
        for e in pf_log:
            if e.get("action") in ("raise", "all_in") and opener_seat is None:
                opener_seat = e.get("seat")
            if e.get("seat") == agg_seat:
                agg_pf_action = e.get("action")
        opener_pos = bot_mod.get_opp_position(state, opener_seat) if opener_seat is not None else None

        if (agg_pos in ("BB", "SB") and agg_pf_action == "call"
            and (agg_pos, opener_pos) in THREEBET_CALL_FREQS):
            base_range = THREEBET_CALL_FREQS[(agg_pos, opener_pos)]
            # apply narrowing manually (same code as original tail)
            pf_raises = bot_mod.count_postflop_raises(state, agg_seat)
            if pf_raises == 0:
                return base_range
            board = state.get("community_cards", [])
            if pf_raises == 1:
                strength = "medium"
                if board and len(board) >= 3:
                    ranks = [c[0] for c in board]
                    if len(ranks) != len(set(ranks)):
                        strength = "strong"
            elif pf_raises == 2:
                strength = "medium"
            else:
                strength = "strong"
            if bot_mod._aggressor_last_action_is_allin(state, agg_seat):
                strength = "strong"
            return bot_mod._narrow_range(base_range, strength, board=board)

        # Fall back to original logic
        return orig(state, agg_seat)
    bot_mod.aggressor_likely_range = patched


# === FIX 3: _narrow_range — board-aware, no empty-subset fallback ==========
def fix3(bot_mod):
    RANK_IDX = bot_mod.RANK_IDX

    def patched(rng_dict, strength, board=None):
        # Static premium subsets (same as original)
        strong = {"AA", "KK", "QQ", "JJ", "AKs", "AKo"}
        medium = strong | {"TT", "99", "88", "AQs", "AQo", "AJs", "AJo",
                            "KQs", "KQo", "T9s", "98s", "87s", "76s"}

        if board and len(board) >= 3:
            tex = bot_mod.board_texture(board)
            if tex != "dry":
                medium = {"AA", "KK", "QQ", "JJ", "TT",
                          "AKs", "AKo", "AQs", "AJs", "KQs"}
                strong = {"AA", "KK", "QQ", "JJ"}

        if strength == "strong":
            subset = {k: v for k, v in rng_dict.items() if k in strong}
        elif strength == "medium":
            subset = {k: v for k, v in rng_dict.items() if k in medium}
        else:
            return rng_dict

        # Board-derived value hands (sets, top-pair, made flushes).
        if board and len(board) >= 3:
            board_ranks = set(c[0] for c in board)
            board_rank_idxs = sorted(RANK_IDX[c[0]] for c in board)
            top_rank = max(c[0] for c in board)
            suits = [c[1] for c in board]
            suit_counts = {s: suits.count(s) for s in set(suits)}
            max_suit = max(suit_counts.values())

            for hand, freq in rng_dict.items():
                # Sets (pocket pair matching board rank)
                if len(hand) == 2 and hand[0] == hand[1] and hand[0] in board_ranks:
                    subset[hand] = max(subset.get(hand, 0.0), freq)
                # Top-pair-good-kicker (one card matches top board rank, kicker ≥ T)
                if len(hand) == 3 and hand.endswith(("s", "o")):
                    h1, h2 = hand[0], hand[1]
                    if (h1 == top_rank and RANK_IDX[h2] >= 8) or \
                       (h2 == top_rank and RANK_IDX[h1] >= 8):
                        subset[hand] = max(subset.get(hand, 0.0), freq * 0.5)
                # Made flushes on 3+ flush boards: any suited combo, weighted
                # 1/4 (suit-match probability for one specific suit).
                if max_suit >= 3 and len(hand) == 3 and hand.endswith("s"):
                    subset[hand] = max(subset.get(hand, 0.0), freq * 0.25)

        # No empty-fallback to full range. If still empty, return tightest
        # possible (top of input range).
        if not subset:
            # Take top 10% of input range by freq as last resort.
            ranked = sorted(rng_dict.items(), key=lambda x: -x[1])
            n = max(1, len(ranked) // 10)
            subset = dict(ranked[:n])
        return subset
    bot_mod._narrow_range = patched


# === Measurement loop ======================================================
def measure(label, fixes):
    b = fresh_bot()
    for f in fixes:
        f(b)

    state = state_27()
    BB = 4
    v_range = b.aggressor_likely_range(state, BB)
    nz = {k: v for k, v in v_range.items() if v > 0}
    eq = b.equity_vs_range(state["your_cards"], state["community_cards"],
                           v_range, n_sims=3000, rng=random.Random(42))

    cfg = b.CONFIG
    eff = min(state["amount_owed"], state["your_stack"])
    callable_pot = state["pot"] - (state["amount_owed"] - eff)
    pot_odds = eff / (callable_pot + eff)
    risk_pct = b.stack_risked_pct(state, eff)
    required = pot_odds + cfg.pot_odds_buffer_normal + cfg.variance_c * (risk_pct ** 2)
    decision = "CALL" if eq >= required else "FOLD"

    sample_keys = list(nz.keys())[:10]
    print(f"\n  {label}")
    print(f"    range size : {len(nz):3d} hands   sample: {sample_keys}{'...' if len(nz)>10 else ''}")
    print(f"    equity     : {eq*100:5.1f}%   required: {required*100:.1f}%   ->  {decision}")
    return eq, required


print("=" * 72)
print("Hand 27 turn-call trace — progressive fixes (KK22 vs flush)")
print("Required equity ≈ 54.4% to call.  Truth: must be a FOLD.")
print("=" * 72)
measure("LAYER 0 — no fixes (original buggy)",     [])
measure("LAYER 1 — fix _preflop_action_log only",  [fix1])
measure("LAYER 1+2 — also fix BB-defender base",   [fix1, fix2])
measure("LAYER 1+2+3 — also fix narrow fallback +board-aware",
                                                    [fix1, fix2, fix3])

print()
print("=" * 72)
print("Equity vs each plausible opponent holding (sanity check)")
print("=" * 72)
b = fresh_bot()
opp_hands = [
    ("Qcfc=flush",       ["Qc", "4c"]),   # actual hand
    ("Acfc=nut flush",   ["Ac", "9c"]),
    ("AKcc=top+nutfd",   ["Ac", "Kc"]),   # would be a flush now (5 clubs)
    ("set of jacks JJ",  ["Js", "Jd"]),
    ("set of sevens 77", ["7s", "7d"]),
    ("set of deuces 22", ["2d", "2h"]),
    ("AK top pair",      ["As", "Kd"]),
    ("KQ top pair K",    ["Qs", "Kd"]),
    ("pure bluff 65o",   ["6s", "5d"]),
]
state = state_27()
for label, opp in opp_hands:
    eq = b.equity_vs_range(state["your_cards"], state["community_cards"],
                           {f"{opp[0][0]}{opp[1][0]}": 1.0},  # single-hand range
                           n_sims=3000, rng=random.Random(42))
    # Better: compute directly via eval7
    import eval7
    me_cards    = [eval7.Card(c) for c in state["your_cards"]]
    opp_cards   = [eval7.Card(c) for c in opp]
    board_cards = [eval7.Card(c) for c in state["community_cards"]]
    deck = [c for c in eval7.Deck()
            if c not in me_cards + opp_cards + board_cards]
    wins, ties, total = 0, 0, 0
    rng = random.Random(42)
    for _ in range(3000):
        rng.shuffle(deck)
        river = deck[0]
        ms = eval7.evaluate(me_cards + board_cards + [river])
        os = eval7.evaluate(opp_cards + board_cards + [river])
        if ms > os: wins += 1
        elif ms == os: ties += 1
        total += 1
    eq_true = (wins + 0.5 * ties) / total
    print(f"  vs {label:<22} -> KK22 equity = {eq_true*100:5.1f}%")
