"""Bust pattern survey for skantbot 7.10.

run_match already returns hand_log with everything we need (action_log,
final_stacks per hand, revealed_cards on showdowns, hand_strengths). We just
need to chain hands to compute per-hand chip deltas, identify big losses,
and classify the patterns.

Output:
  - bust hands (loss >= 2000) with board, action, opponent's revealed hand
  - pattern frequencies across the survey
  - top-N biggest losses with full action log for manual review
"""
import sys, os, json, random
from collections import Counter
sys.path.insert(0, ".")
from sandbox.match import run_match, STARTING_STACK
from harness.opponents.registry import load_pool


SKANT = "skantbot7.11"
SKANT_PATH = "bots/skantbot7.11/bot.py"
LOSS_THRESHOLD = 2000   # hand loss >= this triggers bust classification


def per_hand_deltas(hand_log, bot_id, start_stack):
    """Yield (hand_num, hand_id, pre_stack, post_stack, delta, hand_data)."""
    prev = start_stack
    for h in hand_log:
        post = h["final_stacks"].get(bot_id, prev)
        yield h["hand_num"], h["hand_id"], prev, post, post - prev, h
        prev = post


def classify_bust(hand, bot_id):
    """Categorize a bust pattern. Returns dict of classification fields."""
    board   = hand.get("community_cards", [])
    winners = hand.get("winners", [])
    revealed = hand.get("revealed_cards", {})
    strengths = hand.get("hand_strengths", {})
    log     = hand.get("action_log", [])

    # Board features
    suits = [c[1] for c in board]
    ranks = [c[0] for c in board]
    max_suit = max(suits.count(s) for s in set(suits)) if suits else 0
    paired_board = len(ranks) != len(set(ranks)) if ranks else False

    # Skant role: was skant ever a raiser/all-in?
    skant_seat = None
    for entry in log:
        # Action log doesn't have bot_id, only seat — but engine_results has seats
        pass
    # Try via hand_strengths or revealed_cards instead:
    skant_revealed = revealed.get(bot_id, None)
    skant_strength = strengths.get(bot_id, "?")

    # Opponents who reached showdown (revealed cards != None)
    showdown_opps = [
        (bid, cards, strengths.get(bid, "?"))
        for bid, cards in revealed.items()
        if bid != bot_id and cards
    ]

    # Identify the street where skant invested the most
    # Action log entries have action + amount per seat; without seat→bot mapping
    # we can't easily attribute. Use rough heuristic: look at terminal street.
    streets_in_log = set()
    last_street = "preflop"
    for entry in log:
        a = entry.get("action", "")
        # Estimate street boundary by board card count growth — fallback: river if any of these
    # Easier: just use the length of community_cards
    n_board = len(board)
    final_street = ["preflop","flop","turn","river"][min(n_board - (2 if n_board==0 else 0), 3) if n_board > 0 else 0]
    # Simpler mapping
    if   n_board == 0: final_street = "preflop"
    elif n_board == 3: final_street = "flop"
    elif n_board == 4: final_street = "turn"
    else: final_street = "river"

    # Pattern tags
    tags = []
    if max_suit >= 3:
        tags.append("flush_board")
    if paired_board:
        tags.append("paired_board")
    if max_suit >= 3 and any("Flush" in (strengths.get(o[0], "")) for o in showdown_opps):
        tags.append("opp_made_flush")
    if any("Straight" in strengths.get(o[0], "") for o in showdown_opps):
        tags.append("opp_made_straight")
    if any("Full House" in strengths.get(o[0], "") or "Quads" in strengths.get(o[0], "") for o in showdown_opps):
        tags.append("opp_boat_or_quads")
    if any("Three of" in strengths.get(o[0], "") for o in showdown_opps) and "Three of" not in str(skant_strength):
        tags.append("opp_set")
    if not showdown_opps:
        tags.append("won_without_showdown")  # skant folded without seeing opp's hand
    if "preflop" == final_street:
        tags.append("preflop_only")

    # Per-bot chip investment over the hand from action_log:
    # Map seats to bot_ids via the engine's player list isn't in this dict, but
    # we can reverse-engineer from the action log by tracking bet totals per seat
    # and noting which seats voluntarily acted (i.e. weren't folded immediately).
    seat_bets = {}
    for entry in log:
        seat = entry.get("seat")
        action = entry.get("action")
        amt = entry.get("amount", 0)
        if action in ("small_blind", "big_blind", "raise", "all_in"):
            seat_bets[seat] = amt
        elif action == "call":
            seat_bets[seat] = max(seat_bets.values()) if seat_bets else amt

    return {
        "final_street": final_street,
        "board": board,
        "n_board": n_board,
        "skant_revealed": skant_revealed,
        "skant_strength": skant_strength,
        "showdown_opps": showdown_opps,
        "winners": [w.get("bot_id") for w in winners],
        "tags": "+".join(tags) if tags else "uncategorised",
        "log_len": len(log),
        "action_log": log,
        "seat_bets": seat_bets,
    }


def run_one_match(match_idx, pool_items, n_hands=200, seed=None):
    # Pick 5 random opponents + skant
    if seed is not None:
        random.seed(seed)
    opps = random.sample(pool_items, 5)
    bots = {SKANT: SKANT_PATH}
    for name, path in opps:
        bots[name] = path
    match_id = f"bust_survey_{match_idx:03d}"
    return run_match(match_id, bots, n_hands=n_hands, seed=seed)


def main():
    n_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    n_hands   = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    os.environ["ACTION_TIMEOUT"] = "999999"
    pool = load_pool(include_heldout=True)
    pool_items = list(pool.items())

    all_busts = []
    pattern_counts = Counter()
    total_hands = 0
    total_loss = 0
    total_matches_with_5k = 0

    for i in range(n_matches):
        seed = 1000 + i
        print(f"  match {i+1}/{n_matches} (seed={seed})...", end="", flush=True)
        result = run_one_match(i, pool_items, n_hands=n_hands, seed=seed)
        opp_ids = [b for b in result["bot_ids"] if b != SKANT]
        skant_delta = result["chip_delta"].get(SKANT, 0)
        big_loss_match = skant_delta < -5000
        if big_loss_match:
            total_matches_with_5k += 1
        print(f" Δ={skant_delta:+6.0f}  opps=[{','.join(o[:9] for o in opp_ids)}]"
              + (" [BIG LOSS]" if big_loss_match else ""))

        for hand_num, hand_id, pre, post, delta, hdata in per_hand_deltas(
            result["hands"], SKANT, STARTING_STACK
        ):
            total_hands += 1
            if delta <= -LOSS_THRESHOLD:
                cls = classify_bust(hdata, SKANT)
                bust = {
                    "match_idx": i, "hand_num": hand_num, "hand_id": hand_id,
                    "pre_stack": pre, "post_stack": post, "loss": -delta,
                    **cls, "opp_set": opp_ids
                }
                all_busts.append(bust)
                pattern_counts[cls["tags"]] += 1
                total_loss += -delta

    print()
    print("=" * 80)
    print(f"SUMMARY — {n_matches} matches, {total_hands} hands")
    print(f"  Matches with >5k total loss : {total_matches_with_5k}")
    print(f"  Bust hands (loss >= {LOSS_THRESHOLD})  : {len(all_busts)}")
    print(f"  Total chips lost in busts   : {total_loss}")
    print(f"  Bust frequency              : {len(all_busts)/total_hands*100:.2f}% of hands")
    print()
    print("PATTERN FREQUENCIES")
    print("-" * 80)
    for pat, n in pattern_counts.most_common():
        print(f"  {n:4d}  ({n/len(all_busts)*100:5.1f}%)  {pat}")

    print()
    print("=" * 80)
    print("TOP 10 BIGGEST BUST HANDS")
    print("-" * 80)
    all_busts.sort(key=lambda b: -b["loss"])
    for b in all_busts[:10]:
        opp_summary = " ; ".join(f"{bid}:{cards}={s}" for bid, cards, s in b["showdown_opps"][:2])
        print(f"  hand {b['hand_id']:<36} loss={b['loss']:>6}  "
              f"board={str(b['board']):<28} final_street={b['final_street']:<7}  "
              f"skant_str={b['skant_strength']:<14} | {b['tags']}")
        print(f"      revealed: {b['skant_revealed']}   showdown_opps: {opp_summary}")

    out_path = "harness/results/bust_survey_710.json"
    with open(out_path, "w") as f:
        json.dump({
            "n_matches": n_matches, "n_hands_per": n_hands,
            "total_hands": total_hands,
            "n_busts": len(all_busts),
            "total_loss": total_loss,
            "pattern_counts": dict(pattern_counts),
            "busts": all_busts,
        }, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
