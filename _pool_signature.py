"""V81 §3.1a — Pool behavioral signature.

For each opp in train + heldout, compute (VPIP, PFR, AF, mean_bet_pct_pot, WTSD)
by parsing engine `events` after a series of matches vs skantbot7.13. Outputs
JSON of per-opp stats and prints a train-vs-heldout comparison summary.

This is the gate for §3.2: are train/heldout clearly separated clusters?

Usage:
    python _pool_signature.py [n_matches=40] [n_hands=200]
"""
import sys, json, random
from collections import defaultdict
sys.path.insert(0, ".")
from sandbox.match import run_match
from harness.opponents.registry import (
    load_pool, TRAIN_EXPANDED, UNSEEN_VALIDATION,
)

SKANT = "skantbot7.13"
SKANT_PATH = "bots/skantbot7.13/bot.py"
N_MATCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
N_HANDS = int(sys.argv[2]) if len(sys.argv) > 2 else 200
OUT_PATH = "harness/results/pool_signature_v81.json"


def signature_init():
    return {
        "hands_played": 0,
        "vpip_count": 0,
        "pfr_count": 0,
        "postflop_bets_raises": 0,
        "postflop_calls": 0,
        "bet_pct_pot_sum": 0.0,
        "bet_pct_pot_n": 0,
        "wtsd_count": 0,
    }


def parse_events_into_stats(events, sig_by_bot):
    """Walk events list and update per-bot signature counters."""
    by_hand = defaultdict(list)
    for ev in events:
        by_hand.setdefault("__seq__", []).append(ev)

    # All events are for a single hand here (run_match passes one hand's result).
    # Determine which bots were in the hand (received a blind or preflop action).
    in_hand = set()
    vpip_seen = set()
    pfr_seen = set()
    wtsd_seen = set()
    pot_before = {}   # bot_id -> pot at time of their last bet (for size calc)

    pot_track = 0
    for ev in events:
        t = ev.get("type")
        bid = ev.get("bot_id")
        street = ev.get("street", "preflop")

        if t == "blind":
            if bid:
                in_hand.add(bid)
            continue

        if t == "action":
            action = ev.get("action", "")
            amount = ev.get("amount", 0)
            pot_after = ev.get("pot", pot_track)
            # pot_before this action = pot reported by previous event
            # On preflop, vpip/pfr tracking
            if bid:
                in_hand.add(bid)
                if street == "preflop":
                    if action in ("call", "raise", "all_in"):
                        vpip_seen.add(bid)
                    if action in ("raise", "all_in"):
                        pfr_seen.add(bid)
                else:
                    if action in ("raise", "all_in"):
                        sig_by_bot[bid]["postflop_bets_raises"] += 1
                        # Bet sizing: amount / pot_before this raise
                        # pot reported on this event is pot_after, so use prior pot_track
                        if pot_track > 0 and amount > 0:
                            sig_by_bot[bid]["bet_pct_pot_sum"] += amount / pot_track
                            sig_by_bot[bid]["bet_pct_pot_n"] += 1
                    elif action == "call":
                        sig_by_bot[bid]["postflop_calls"] += 1
            pot_track = pot_after
            continue

        if t == "showdown":
            # showdown.revealed: {bot_id: cards} for all bots seen at showdown.
            for wbid in ev.get("revealed", {}) or {}:
                wtsd_seen.add(wbid)

    # Finalize per-bot counters for this hand
    for bid in in_hand:
        sig_by_bot[bid]["hands_played"] += 1
        if bid in vpip_seen:
            sig_by_bot[bid]["vpip_count"] += 1
        if bid in pfr_seen:
            sig_by_bot[bid]["pfr_count"] += 1
        if bid in wtsd_seen:
            sig_by_bot[bid]["wtsd_count"] += 1


def finalize(sig):
    h = max(sig["hands_played"], 1)
    pf_actions = sig["postflop_bets_raises"] + sig["postflop_calls"]
    af = (sig["postflop_bets_raises"] / sig["postflop_calls"]
          if sig["postflop_calls"] > 0 else None)
    return {
        "hands_played": sig["hands_played"],
        "vpip": sig["vpip_count"] / h,
        "pfr": sig["pfr_count"] / h,
        "af": af,
        "postflop_calls": sig["postflop_calls"],
        "postflop_bets_raises": sig["postflop_bets_raises"],
        "mean_bet_pct_pot": (
            sig["bet_pct_pot_sum"] / max(sig["bet_pct_pot_n"], 1)
            if sig["bet_pct_pot_n"] > 0 else None
        ),
        "wtsd": sig["wtsd_count"] / h,
        "postflop_actions": pf_actions,
    }


def collect(pool, label):
    sig_by_bot = defaultdict(signature_init)
    pool_items = list(pool.items())
    random.seed(42)
    print(f"\n[{label}] Running {N_MATCHES} matches × {N_HANDS} hands "
          f"vs {len(pool_items)} opps", flush=True)
    for i in range(N_MATCHES):
        seed = random.randint(0, 1_000_000)
        opps = random.sample(pool_items, min(5, len(pool_items)))
        bots = {SKANT: SKANT_PATH}
        for oid, opath in opps:
            bots[oid] = opath
        res = run_match(f"sig_{label}_{i:03d}", bots, n_hands=N_HANDS, seed=seed)
        for h in res["hands"]:
            parse_events_into_stats(h.get("events", []), sig_by_bot)
        if (i + 1) % 10 == 0:
            print(f"  [{label}] match {i+1}/{N_MATCHES}", flush=True)
    return {bid: finalize(sig) for bid, sig in sig_by_bot.items()}


def summarize(label, stats):
    keys = ("vpip", "pfr", "af", "mean_bet_pct_pot", "wtsd")
    print(f"\n=== {label} ===")
    print(f"{'opp':<22} {'hands':>6} {'VPIP':>6} {'PFR':>6} {'AF':>6} "
          f"{'bet%pot':>8} {'WTSD':>6}")
    for bid in sorted(stats):
        s = stats[bid]
        if s["hands_played"] < 20:
            continue
        bpp = s["mean_bet_pct_pot"]
        bpp_s = f"{bpp:.2f}" if bpp is not None else "  -- "
        af = s["af"]
        af_s = f"{af:.2f}" if af is not None else "  -- "
        print(f"{bid:<22} {s['hands_played']:>6} {s['vpip']:.2f}   "
              f"{s['pfr']:.2f}   {af_s:>5}   {bpp_s:>8}   {s['wtsd']:.2f}")

    # Aggregates (skip opp_id=skantbot)
    other = [s for bid, s in stats.items()
             if bid != SKANT and s["hands_played"] >= 20]
    if not other:
        return None
    def med(key, default=None):
        vals = [s[key] for s in other if s.get(key) is not None]
        if not vals: return default
        vals.sort()
        return vals[len(vals) // 2]
    def mean(key, default=None):
        vals = [s[key] for s in other if s.get(key) is not None]
        return sum(vals)/len(vals) if vals else default
    agg = {
        "n_opps": len(other),
        "vpip_median": med("vpip"),
        "vpip_mean": mean("vpip"),
        "pfr_median": med("pfr"),
        "af_median": med("af"),
        "af_mean": mean("af"),
        "bet_pct_pot_median": med("mean_bet_pct_pot"),
        "wtsd_median": med("wtsd"),
    }
    print(f"\n  median VPIP={agg['vpip_median']:.2f}  "
          f"PFR={agg['pfr_median']:.2f}  AF={agg['af_median']:.2f}  "
          f"bet%pot={agg['bet_pct_pot_median'] or 0:.2f}  "
          f"WTSD={agg['wtsd_median']:.2f}")
    return agg


def main():
    train_stats = collect(TRAIN_EXPANDED, "train")
    heldout_stats = collect(UNSEEN_VALIDATION, "heldout")

    train_agg = summarize("TRAIN_EXPANDED", train_stats)
    heldout_agg = summarize("UNSEEN_VALIDATION", heldout_stats)

    print("\n=== TRAIN vs HELDOUT DIFFERENCE ===")
    if train_agg and heldout_agg:
        for k in ("vpip_median", "pfr_median", "af_median",
                  "bet_pct_pot_median", "wtsd_median"):
            t = train_agg[k] or 0
            h = heldout_agg[k] or 0
            ratio = (h / t) if t else float("inf")
            print(f"  {k:<22}  train={t:.3f}  heldout={h:.3f}  "
                  f"ratio_h/t={ratio:.2f}")

    out = {
        "skant": SKANT, "n_matches": N_MATCHES, "n_hands": N_HANDS,
        "train": train_stats, "heldout": heldout_stats,
        "train_agg": train_agg, "heldout_agg": heldout_agg,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
