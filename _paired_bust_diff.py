"""V81 §3.1d — Paired bust difference (A vs B on shared seeds + match_ids).

For each (seed, opp_set), runs bot A and bot B separately as `<hero_id>` with
the SAME match_id so both share identical hand_ids → identical bot RNG seeds.
Counts $LOSS_THRESHOLD-bust hands, classifies them via _bust_analyze.classify_bust,
reports paired per-family count + dollar diff.

CAVEAT: Two pool opponents (`uniform_random`, `aggressor`) do NOT seed from
hand_id, so per-match deltas have noise from those opps' randomness. Aggregate
diffs at N≥60 matches are stable (LLN). For sharper comparisons exclude these
two opps from the pool sample.

Usage:
    python _paired_bust_diff.py <bot_a_path> <bot_b_path> <pool_type> [n_matches]
        pool_type ∈ {train, heldout, combined, train_v81, heldout_v81}
"""
import sys, json, random
from collections import Counter, defaultdict
sys.path.insert(0, ".")
from sandbox.match import run_match, STARTING_STACK
from harness.opponents import registry
import importlib.util


BOT_A = sys.argv[1] if len(sys.argv) > 1 else "bots/skantbot7.13/bot.py"
BOT_B = sys.argv[2] if len(sys.argv) > 2 else "bots/skantbot8/bot.py"
POOL_TYPE = sys.argv[3] if len(sys.argv) > 3 else "train"
N_MATCHES = int(sys.argv[4]) if len(sys.argv) > 4 else 60
N_HANDS = 200
LOSS_THRESHOLD = 2000
HERO_ID = "hero"   # same id for both bots so opps see identical opponents

ba_spec = importlib.util.spec_from_file_location("_ba", "_bust_analyze.py")
ba = importlib.util.module_from_spec(ba_spec); ba_spec.loader.exec_module(ba)


def resolve_pool(pool_type):
    if pool_type == "train":
        return registry.load_pool(include_heldout=False)
    if pool_type == "heldout":
        full = registry.load_pool(include_heldout=True)
        tr = registry.load_pool(include_heldout=False)
        return {k: v for k, v in full.items() if k not in tr}
    if pool_type == "combined":
        return registry.load_pool(include_heldout=True)
    if pool_type == "train_v81":
        return getattr(registry, "TRAIN_EXPANDED_V81")
    if pool_type == "heldout_v81":
        return getattr(registry, "UNSEEN_VALIDATION_V81")
    raise ValueError(f"unknown pool_type: {pool_type}")


def collect_busts(hero_path, seed_opp_pairs, label):
    busts = []
    total_loss = 0
    total_delta = 0
    for i, (seed, opps) in enumerate(seed_opp_pairs):
        bots = {HERO_ID: hero_path}
        for oid, opath in opps:
            bots[oid] = opath
        # CRN: same match_id across A and B → same hand_ids → same bot RNG.
        # Bots' decisions diverge only because their code differs.
        res = run_match(f"pdiff_{i:03d}", bots, n_hands=N_HANDS, seed=seed)
        total_delta += res["final_stacks"][HERO_ID] - STARTING_STACK
        prev = STARTING_STACK
        for h in res["hands"]:
            post = h["final_stacks"].get(HERO_ID, prev)
            delta = post - prev
            if delta <= -LOSS_THRESHOLD:
                cls = ba.classify_bust(h, HERO_ID)
                cls.update({"match_idx": i, "loss": -delta,
                            "hand_id": h["hand_id"]})
                busts.append(cls)
                total_loss += -delta
            prev = post
        if (i + 1) % 20 == 0:
            print(f"  [{label}] match {i+1}/{len(seed_opp_pairs)}: "
                  f"busts={len(busts)} loss=${total_loss:,}", flush=True)
    return busts, total_delta, total_loss


def family_counts(busts):
    c = Counter()
    losses = defaultdict(int)
    for b in busts:
        fam = b.get("pattern_family") or b.get("pattern") or "unknown"
        c[fam] += 1
        losses[fam] += b.get("loss", 0)
    return c, losses


def main():
    pool = resolve_pool(POOL_TYPE)
    pool_items = list(pool.items())
    random.seed(42)
    # Build shared (seed, opp_sample) pairs ONCE — both bots see identical sets
    seed_opp_pairs = []
    for _ in range(N_MATCHES):
        seed = random.randint(0, 1_000_000)
        opps = random.sample(pool_items, min(5, len(pool_items)))
        seed_opp_pairs.append((seed, opps))

    print(f"A = {BOT_A}")
    print(f"B = {BOT_B}")
    print(f"Pool = {POOL_TYPE} ({len(pool)} opps), N_MATCHES = {N_MATCHES}")

    print("\n[A] running...")
    busts_a, delta_a, loss_a = collect_busts(BOT_A, seed_opp_pairs, "A")
    print(f"[A] final: busts={len(busts_a)}  total_chip_delta={delta_a:+}  "
          f"bust_loss=${loss_a:,}")

    print("\n[B] running...")
    busts_b, delta_b, loss_b = collect_busts(BOT_B, seed_opp_pairs, "B")
    print(f"[B] final: busts={len(busts_b)}  total_chip_delta={delta_b:+}  "
          f"bust_loss=${loss_b:,}")

    fa, la = family_counts(busts_a)
    fb, lb = family_counts(busts_b)
    fams = sorted(set(fa) | set(fb))

    print("\n=== Per-family bust diff (B - A) ===")
    print(f"{'family':<42} {'A_n':>4} {'B_n':>4} {'Δn':>5}  "
          f"{'A_$':>10} {'B_$':>10} {'Δ$':>10}")
    for fam in fams:
        dn = fb.get(fam, 0) - fa.get(fam, 0)
        dl = lb.get(fam, 0) - la.get(fam, 0)
        print(f"{str(fam):<42} {fa.get(fam,0):>4} {fb.get(fam,0):>4} "
              f"{dn:>+5}  ${la.get(fam,0):>9,} ${lb.get(fam,0):>9,} "
              f"${dl:>+9,}")

    print("\n=== Totals ===")
    print(f"A: {len(busts_a)} busts, ${loss_a:,} loss, chip_delta {delta_a:+,}")
    print(f"B: {len(busts_b)} busts, ${loss_b:,} loss, chip_delta {delta_b:+,}")
    print(f"Δ busts (B-A):  {len(busts_b) - len(busts_a):+}")
    print(f"Δ loss (B-A):   ${loss_b - loss_a:+,}")
    print(f"Δ delta (B-A):  {delta_b - delta_a:+,}")

    out_path = (f"harness/results/paired_bust_diff_"
                f"{POOL_TYPE}_n{N_MATCHES}.json")
    with open(out_path, "w") as f:
        json.dump({
            "bot_a": BOT_A, "bot_b": BOT_B, "pool_type": POOL_TYPE,
            "n_matches": N_MATCHES,
            "totals": {
                "a_n_busts": len(busts_a), "b_n_busts": len(busts_b),
                "a_loss": loss_a, "b_loss": loss_b,
                "a_delta": delta_a, "b_delta": delta_b,
            },
            "per_family": {
                fam: {"a_n": fa.get(fam,0), "b_n": fb.get(fam,0),
                      "a_loss": la.get(fam,0), "b_loss": lb.get(fam,0)}
                for fam in fams
            },
        }, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
