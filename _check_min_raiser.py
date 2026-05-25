"""Verify 7.11 preserves Phase 2a's original min_raiser win.

Per memory project_state_skantbot: 7.7's Phase 2a fix went from
HU vs min_raiser -2,100 -> +5,355 chips/match. The 7.11 commitment override
gates Phase 2a; this test confirms the original min_raiser preservation
because min_raiser bets are small (don't bloat pot, don't hit committed_bet_pct).

Acceptance: 7.11 vs min_raiser HU mean Δ must be >= 7.10's by at least
not regressing more than 1000 chips. If 7.11 regresses sharply, our
gating is too aggressive and Phase 2a's purpose is being undone."""
import sys, json
sys.path.insert(0, ".")
from harness.match_runner import compare, aggregate_by_opponent


SKANT_10 = "bots/skantbot7.10/bot.py"
SKANT_11 = "bots/skantbot7.11/bot.py"
MIN_RAISER = "harness/opponents/archetypes/min_raiser/bot.py"


def run(skant_path, label):
    pool = {"min_raiser": MIN_RAISER}
    print(f"\n=== {label} vs min_raiser HU (n_seeds=100) ===")
    results = compare(
        bot_a_path=skant_path, bot_b_path=skant_path,
        opponent_pool=pool,
        n_seeds=100, n_workers=12, n_hands=400,
        show_progress=False, mode="hu",
    )
    # HU return: dict keyed by opponent name with stats fields directly
    mr = results.get("min_raiser", {})
    print(f"  a_mean    = {mr.get('a_mean', 0):+.0f}")
    print(f"  a_stderr  = {mr.get('a_stderr', 0):+.0f}")
    print(f"  n         = {mr.get('n', 0)}")
    return mr


def main():
    r10 = run(SKANT_10, "7.10")
    r11 = run(SKANT_11, "7.11")
    d = r11.get("a_mean", 0) - r10.get("a_mean", 0)
    pooled_se = ((r10.get("a_stderr", 0)**2 + r11.get("a_stderr", 0)**2)**0.5)
    print()
    print(f"Δ (7.11 - 7.10) = {d:+.0f} chips/match  (pooled stderr {pooled_se:.0f})")
    if r11.get("a_mean", 0) < 3000:
        print("  ⚠ 7.11 HU vs min_raiser dropped below +3k — investigate")
    elif d < -1000:
        print(f"  ⚠ regression of {-d:.0f} chips — check if dampening too aggressive")
    else:
        print("  ✓ Phase 2a's min_raiser win preserved.")


if __name__ == "__main__":
    main()
