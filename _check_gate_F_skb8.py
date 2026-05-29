"""V81 Step 2 — Gate F: per-opp preservation checks.

skantbot8 vs maniac_aggro HU and vs super_nit HU must not regress by more
than 500 chips/match vs 7.13. Catches the failure modes:
  - over-loosening vs maniac_aggro (their already-high-mean wouldn't trigger
    a narrowing — but the maniac-modifier might over-trust their bluffs)
  - over-narrowing vs super_nit (nit-modifier narrows harder, may fold to
    super_nit's rare big bets unnecessarily)
"""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare

OPPS = {
    "maniac_aggro": "harness/opponents/archetypes/maniac_aggro/bot.py",
    "super_nit": "harness/opponents/archetypes/super_nit/bot.py",
}


def run(path, label, opp_id, opp_path):
    res = compare(
        bot_a_path=path, bot_b_path=path,
        opponent_pool={opp_id: opp_path},
        n_seeds=100, n_workers=4, n_hands=400,
        show_progress=False, mode="hu",
    )
    s = res[opp_id]
    print(f"{label} vs {opp_id} HU: {s['a_mean']:+.0f} ± {s['a_stderr']:.0f}")
    return s


def main():
    fails = []
    for opp_id, opp_path in OPPS.items():
        r13 = run("bots/skantbot7.13/bot.py", "7.13", opp_id, opp_path)
        r8 = run("bots/skantbot8/bot.py",    "skantbot8", opp_id, opp_path)
        d = r8["a_mean"] - r13["a_mean"]
        se = (r13["a_stderr"]**2 + r8["a_stderr"]**2) ** 0.5
        sigma = d / se if se > 0 else 0.0
        print(f"  Δ (skantbot8 - 7.13) = {d:+.0f}  σ={sigma:+.2f}\n")
        if d < -500:
            fails.append((opp_id, d, sigma))

    if fails:
        print("✗ GATE F FAIL:")
        for opp, d, sig in fails:
            print(f"   vs {opp}: Δ={d:+.0f} (> 500 chip drop)")
        sys.exit(1)
    print("✓ GATE F PASS: no >500 chip regression vs maniac_aggro or super_nit")


if __name__ == "__main__":
    main()
