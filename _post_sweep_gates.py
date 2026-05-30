"""V81 §8.4 — Post-sweep gate suite for skantbot8.1.

Runs all critical gates on the freshly-built skantbot8.1 (= skantbot8 + V81
sweep best-trial params) and compares against skantbot7.13 baseline and the
skantbot8 manual-default ship candidate.

Deterministic failure rule (locked in plan amendment):
    If ANY hard gate (B, C, D, E, F) fails → skantbot8.1 is NOT shipped.
    The fallback ship candidate is skantbot8 (= 7.13 + #1 manual default).

Usage:
    python _post_sweep_gates.py
"""
import sys, subprocess
sys.path.insert(0, ".")

RESULTS = "harness/results"
gates_passed = []
gates_failed = []


def run(label, cmd, log_path):
    print(f"\n=== {label} ===")
    print(f"  cmd: {' '.join(cmd)}")
    with open(log_path, "w") as logf:
        rc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT).returncode
    with open(log_path) as f:
        tail = "".join(f.readlines()[-15:])
    print(tail)
    if rc == 0:
        gates_passed.append(label)
    else:
        gates_failed.append((label, log_path))
    return rc


def main():
    # ---- Validator + tests + CRN (Gate A) ----
    run("Gate A: validator on skantbot8.1/bot.py",
        [".venv/bin/python", "sandbox/validator.py", "bots/skantbot8.1/bot.py"],
        f"{RESULTS}/gate_A_validator_skb81.log")
    run("Gate A: pytest tests/",
        [".venv/bin/python", "-m", "pytest", "tests/", "-q"],
        f"{RESULTS}/gate_A_pytest_skb81.log")
    # CRN check needs the registry's TUNABLE_PATH pointing at skb81_dev.
    # Use direct call instead of editing registry.
    run("Gate A: CRN on skantbot8.1_dev",
        [".venv/bin/python", "-c", """
import sys; sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent
from harness.opponents.registry import load_pool
pool = load_pool(include_heldout=False)
res = compare(
    bot_a_path="harness/skantbot8.1_dev/bot.py",
    bot_b_path="harness/skantbot8.1_dev/bot.py",
    opponent_pool=pool, n_seeds=5, n_workers=12, n_hands=200,
    show_progress=False, mode="6max", n_tables=5,
)
agg = aggregate_by_opponent(res)
nonzero = [(opp, s["paired_diff_mean"]) for opp, s in agg.items()
           if abs(s.get("paired_diff_mean", 0)) > 1e-9]
if nonzero:
    print("FAIL — CRN broken:")
    for opp, pd in nonzero: print(f"  {opp}: {pd}")
    sys.exit(1)
print(f"PASS — paired_diff_mean == 0 for all {len(agg)} opps")
"""],
        f"{RESULTS}/gate_A_crn_skb81.log")

    # ---- Gate B: min_raiser HU on skantbot8.1 ----
    run("Gate B: skantbot8.1 vs min_raiser HU >= +5000",
        [".venv/bin/python", "-c", """
import sys; sys.path.insert(0, ".")
from harness.match_runner import compare
MIN_RAISER = "harness/opponents/archetypes/min_raiser/bot.py"
def go(path, lbl):
    r = compare(bot_a_path=path, bot_b_path=path,
                opponent_pool={"min_raiser": MIN_RAISER},
                n_seeds=100, n_workers=4, n_hands=400,
                show_progress=False, mode="hu")["min_raiser"]
    print(f"{lbl}: {r['a_mean']:+.0f} ± {r['a_stderr']:.0f}")
    return r
r13 = go("bots/skantbot7.13/bot.py", "7.13")
r8  = go("bots/skantbot8/bot.py",    "skantbot8 (#1 only)")
r81 = go("bots/skantbot8.1/bot.py",  "skantbot8.1 (sweep best)")
print(f"Δ (skb8.1 - skb8)   = {r81['a_mean']-r8['a_mean']:+.0f}")
print(f"Δ (skb8.1 - 7.13)   = {r81['a_mean']-r13['a_mean']:+.0f}")
if r81["a_mean"] < 5000:
    print(f"FAIL: skb8.1 vs min_raiser HU = {r81['a_mean']:+.0f} < +5000")
    sys.exit(1)
print("PASS")
"""],
        f"{RESULTS}/gate_B_min_raiser_skb81.log")

    # ---- Gate D + E: paired-diff vs 7.13 on V81 pools (n_seeds=40 per §8.4) ----
    run("Gate D: skantbot8.1 vs 7.13 on TRAIN_EXPANDED_V81 (n=40)",
        [".venv/bin/python", "_paired_diff_skb8_vs_713.py",
         "train_v81", "40", "20", "bots/skantbot7.13/bot.py",
         "bots/skantbot8.1/bot.py"],
        f"{RESULTS}/gate_D_skb81_vs_713_train_v81.log")
    run("Gate E: skantbot8.1 vs 7.13 on UNSEEN_VALIDATION_V81 (n=40)",
        [".venv/bin/python", "_paired_diff_skb8_vs_713.py",
         "heldout_v81", "40", "20", "bots/skantbot7.13/bot.py",
         "bots/skantbot8.1/bot.py"],
        f"{RESULTS}/gate_E_skb81_vs_713_heldout_v81.log")

    # Also vs skantbot8 (does sweep actually improve over manual default?)
    run("Bonus: skantbot8.1 vs skantbot8 on HELDOUT_V81 (n=40)",
        [".venv/bin/python", "_paired_diff_skb8_vs_713.py",
         "heldout_v81", "40", "20", "bots/skantbot8/bot.py",
         "bots/skantbot8.1/bot.py"],
        f"{RESULTS}/bonus_skb81_vs_skb8_heldout_v81.log")

    # ---- Gate F: maniac/super_nit HU ----
    run("Gate F: skantbot8.1 vs maniac/super_nit HU",
        [".venv/bin/python", "-c", """
import sys; sys.path.insert(0, ".")
from harness.match_runner import compare
OPPS = {"maniac_aggro": "harness/opponents/archetypes/maniac_aggro/bot.py",
        "super_nit":     "harness/opponents/archetypes/super_nit/bot.py"}
fails = []
for o, p in OPPS.items():
    r13 = compare(bot_a_path="bots/skantbot7.13/bot.py",
                  bot_b_path="bots/skantbot7.13/bot.py",
                  opponent_pool={o: p}, n_seeds=100, n_workers=4,
                  n_hands=400, show_progress=False, mode="hu")[o]
    r81 = compare(bot_a_path="bots/skantbot8.1/bot.py",
                  bot_b_path="bots/skantbot8.1/bot.py",
                  opponent_pool={o: p}, n_seeds=100, n_workers=4,
                  n_hands=400, show_progress=False, mode="hu")[o]
    d = r81["a_mean"] - r13["a_mean"]
    print(f"  vs {o}: 7.13={r13['a_mean']:+.0f} skb81={r81['a_mean']:+.0f} Δ={d:+.0f}")
    if d < -500:
        fails.append((o, d))
if fails:
    for o, d in fails: print(f"FAIL vs {o}: Δ={d:+.0f}")
    sys.exit(1)
print("PASS: no >500 chip regression vs maniac/super_nit")
"""],
        f"{RESULTS}/gate_F_skb81.log")

    # Gate C bust survey is SLOW (~15 min). Run last in sequence.
    run("Gate C-part1: skantbot8.1 bust survey heldout_v81 (n=100)",
        [".venv/bin/python", "_bust_survey_param.py", "skantbot8.1",
         "bots/skantbot8.1/bot.py", "heldout_v81", "100"],
        f"{RESULTS}/gate_C_skb81_bust_survey.log")
    run("Gate C-part2: bust class comparison vs 7.13 baseline",
        [".venv/bin/python", "_gate_C_bust_compare.py",
         "harness/results/bust_survey_skantbot7.13_heldout_v81_n100.json",
         "harness/results/bust_survey_skantbot8.1_heldout_v81_n100.json"],
        f"{RESULTS}/gate_C_skb81_compare.log")

    # Summary
    print(f"\n{'=' * 60}\n  POST-SWEEP GATE SUMMARY\n{'=' * 60}")
    print(f"PASSED ({len(gates_passed)}):")
    for g in gates_passed:
        print(f"  ✓ {g}")
    if gates_failed:
        print(f"\nFAILED ({len(gates_failed)}):")
        for g, p in gates_failed:
            print(f"  ✗ {g} (log: {p})")
        print("\n→ Deterministic rule: ship skantbot8 (= 7.13 + #1) instead.")
        sys.exit(1)
    print("\n→ All gates passed. skantbot8.1 is the new ship candidate.")


if __name__ == "__main__":
    main()
