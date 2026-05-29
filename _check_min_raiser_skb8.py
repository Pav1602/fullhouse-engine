"""skantbot8 vs min_raiser HU preservation gate.
Gate threshold: skantbot8 vs min_raiser HU >= +3000 chips/match (hard floor —
this is the structural fix from 7.11 that all later changes must preserve).
The Δ vs 7.13 is also reported."""
import sys
sys.path.insert(0, ".")
from harness.match_runner import compare

MIN_RAISER = "harness/opponents/archetypes/min_raiser/bot.py"


def run(path, label):
    res = compare(
        bot_a_path=path, bot_b_path=path,
        opponent_pool={"min_raiser": MIN_RAISER},
        n_seeds=100, n_workers=4, n_hands=400,
        show_progress=False, mode="hu",
    )
    mr = res["min_raiser"]
    print(f"{label} vs min_raiser HU: {mr['a_mean']:+.0f} ± {mr['a_stderr']:.0f}")
    return mr


def main():
    r13 = run("bots/skantbot7.13/bot.py", "7.13")
    r8 = run("bots/skantbot8/bot.py", "skantbot8")
    d = r8["a_mean"] - r13["a_mean"]
    se = (r13["a_stderr"] ** 2 + r8["a_stderr"] ** 2) ** 0.5
    sigma = d / se if se > 0 else 0.0
    print(f"\nΔ (skantbot8 - 7.13) = {d:+.0f} chips/match "
          f"(pooled SE {se:.0f}, σ={sigma:+.2f})")

    if r8["a_mean"] < 3000:
        print("✗ FAIL: skantbot8 dropped below +3000 vs min_raiser")
        sys.exit(1)
    print("✓ GATE PASS: min_raiser HU preserved (>=+3000)")


if __name__ == "__main__":
    main()
