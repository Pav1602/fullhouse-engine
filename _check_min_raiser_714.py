"""7.14 vs min_raiser HU preservation check.
Gate: 7.14 HU vs min_raiser >= +3000 chips/match (tightened equity_call_threshold
could fold to min-raises; this catches it)."""
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

r13 = run("bots/skantbot7.13/bot.py", "7.13")
r14 = run("bots/skantbot7.14/bot.py", "7.14")
d = r14["a_mean"] - r13["a_mean"]
se = (r13["a_stderr"]**2 + r14["a_stderr"]**2)**0.5
sigma = d / se if se > 0 else 0
print(f"\nΔ (7.14 - 7.13) = {d:+.0f} chips/match (pooled SE {se:.0f}, σ={sigma:+.2f})")
if r14["a_mean"] < 3000:
    print("✗ FAIL: 7.14 dropped below +3000 vs min_raiser")
    sys.exit(1)
else:
    print("✓ GATE 2 PASS: min_raiser HU preserved")
