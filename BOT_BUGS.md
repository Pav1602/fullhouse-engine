# Bot Bugs

Potential issues found during harness development. **Do not fix these here** —
they are in Pav's code. Review with Pav before submission.

---

## [CRITICAL] skantbot3 fails tournament validator

**File:** `bots/skantbot3/bot (1).py`  
**Detected:** `python3 sandbox/validator.py "bots/skantbot3/bot (1).py"`

**Error:**
```
❌ FAILED  —  bots/skantbot3/bot (1).py
Errors:
  ✗ Forbidden import: 'os' — bots may not use network, filesystem, or subprocess modules.
```

**Root cause:** `import os` at line 37 is needed to read `SKANT_*` environment
variables via `load_config_from_env()`. The tournament validator's static AST
check flags this as a forbidden import regardless of how `os` is used.

**Impact:** If submitted as-is, skantbot3 will be **rejected at validation**
before the tournament even starts.

**Fix options (Pav to decide):**

1. **Remove env-var loading before submission** — delete `load_config_from_env()`,
   hard-code the best params found by the Optuna sweep into the default `Config`
   values, and remove `import os`. The harness shim (`harness/skantbot_tunable/bot.py`)
   can still inject params via env vars during sweeps since it calls the internal
   module directly and doesn't go through the validator.

2. **Re-implement env loading without `os`** — use `__import__('os').environ` or
   look for another validator-safe approach (risky, may be caught by runtime checks).

**Recommended:** Option 1. Once the sweep finds best params, hard-code them as
the `Config` defaults and strip `import os` for the final submission.

### Leak 2 (over-fold to all-ins)
`pot_odds = owed / (pot + owed)` uses uncapped owed when opps bet exceeds bot stack. Affects shove-calling frequency in HU. Mechanical fix is `effective_owed = min(owed, stack)`. Cannot ship without re-tuning `equity_call_threshold`, `pot_odds_buffer_normal`, `variance_c` against the train+heldout pools — Optuna sweep recommended. Quick fix loses ~1700 chips/match on heldout. See `REMEDIATION_PLAN_hand38.md` Stage 3.

## [RESOLVED in 7.4] Stages 1+2 narrowing + hand 20 paired-board regression

- count_aggressors/count_my_raises now filter by preflop street
- aggressor_likely_range narrows on postflop aggression
- Paired boards with 1 postflop raise narrow to "strong" subset
  (prevents TP-J cooler on paired-board barrels — see hand 20)
- See REMEDIATION_PLAN_v74.md, PATH_1_5_HAND_20.md, BUST_LOG_HAND_INDEX.md
- Heldout vs Fix-A4-only: -327 chips/match avg (accepted as cost of hand 20 fix)

## [DEFERRED to 7.5] Leak 2 — pot-odds uses uncapped owed

- `pot_odds = owed / (pot + owed)` ignores stack cap when opp shoves > bot stack
- Bot over-folds to all-ins (hand 25 in Pav's bust: folded pair+OESD+FD to A-high bluff)
- Mechanical fix: `effective_owed = min(owed, stack)`. Requires full Optuna re-tune.
- Plan: REMEDIATION_PLAN_v75.md

## [DEFERRED to 7.5] Mode A — over-aggression in c-bet/barrel

- Bot c-bets/barrels too often with marginal hands, builds big pots, folds to raises
- Caused 7 of 12 big losses in Pav's bust (hands 1, 2, 7, 12, 18, 20, 32)
- Fix: lower cbet_freq_base, bluff_freq_ip, bluff_freq_oop. Must be done with Stage 3.

## [KNOWN-MINOR — fix in 7.5] Bust regression test cleanup

- tests/test_pav_bust_regression.py::test_hand_18 is MC-flaky (equity ~ required_eq threshold)
- tests/test_pav_bust_regression.py::test_hand_20 uses board cards that don't match the
  real hand 20 from pav_skantbot_7_bust.txt (real board was 8h 2c Jd | 2h, not 2s Js Qs | 3c).
  The bot folds in both, but for different reasons. Fix in 7.5 cycle.

## [DEFERRED to 7.6] Stage B pot-odds fix is incomplete — caused hand-38 regression in 7.5

- Stage B (7.5) applied `effective_owed = min(owed, stack)` but `pot_odds =
  effective_owed / (pot + effective_owed)` still uses the raw `state["pot"]`,
  which includes the opponent's UNCALLABLE excess when opp shoves > bot stack.
- Numerator capped, denominator not. In all-in-over-stack spots pot_odds is
  understated (hand 38: required_eq ~47% -> ~7%), so the bot calls thin.
- Result: skantbot7.5 CALLS hand 38 (the catastrophic call). 7.3 and 7.4 fold it.
  This is a regression on the single most important test case in the project.
- Correct fix: cap `pot` to the callable amount (raw pot minus opp's uncallable
  excess). Re-tuning the equity thresholds against the corrected formula likely
  needs a fresh Optuna sweep.
- 7.5 did NOT ship. `v7.4-stable` remains the submission. See STAGE_EF_FINDINGS.md.
- REMEDIATION_PLAN_v75.md's claim "Stage B doesn't change hand 38" is false.

## [BUG — test infra] hand-38 regression-test assertions are corrupted

- tests/test_hand_38_leak.py: `test_hand_38_v74_folds`, `test_hand_38_v75_folds`
  and `test_hand_38_bot_decision_overall` all assert `== "call"` while their
  docstrings say "must fold"; the "POST-FIX assertion" comments are copy-paste
  duplicates of the pre-fix code.
- tests/test_pav_bust_regression_v75.py::test_hand_38 asserts `call` with a
  flop-checked action sequence that doesn't match the bust log (real line:
  flop-raise + turn-shove).
- Running pytest as-is would green-light a bot that makes the hand-38
  catastrophic call. Correct expected action for hand 38 is FOLD. Repair the
  assertions before relying on these suites.

## [RESOLVED in 7.6] Leak 1, Leak 2, and Bug C

skantbot7.6 (`bots/skantbot7.6/bot.py`, branch `skantbot7.6/dev`) fixes both
structural leaks plus a nondeterminism bug found during verification:

- **Leak 2 / Bug A** — pot-odds now divides by the *callable* pot
  (`pot - (owed - effective_owed)`), excluding the opponent's uncallable excess;
  numerator capped via `effective_owed`; SPR likewise. The v75 Stage-B "fix"
  capped only the numerator — incomplete, and the cause of the 7.5 regression.
- **Leak 1 / Bug B** — `aggressor_likely_range` now narrows to the tightest
  tier when the aggressor's last action was an all-in
  (`_aggressor_last_action_is_allin`). Previously a turn shove was modelled as
  "medium" (incl. AK-high), over-stating A8dd equity ~2x (~0.49 vs true ~0.25).
- **Bug C** — the equity Monte Carlo used unseeded global `random`, and
  `get_hand_rng` seeded from process-randomised `hash()`. Fixed: seeded `rng`
  threaded through both equity functions; `get_hand_rng` uses `zlib.crc32`. The
  bot is now deterministic given game state (verified cross-process).

hand 38 now folds for sound reasons (correct pot-odds vs a correctly-narrowed
range), not 7.4's bug-cancellation. All exit criteria met; heldout +183/match
vs 7.4; +875/+1500 vs the adversarial bots. See STAGE_EF_FINDINGS.md. **7.6 is
the ship candidate.** The corrupted hand-38 test assertions (above) were fixed
in 7.6 Stage 0.

## [STILL OPEN — 7.7] Mode A — over-aggression in c-bet/barrel

7.6 does NOT fix Mode A (over-wide c-bet/barrel → bloated pots, 7 of 12 big
losses in Pav's bust). Partial mitigation: 7.6's correct fold-to-shove means
when a Mode-A pot gets jammed on, the bot folds correctly instead of punting —
so Mode A's *tail* risk is smaller, but the root frequency issue remains. Full
fix is a 7.7 cycle (lower cbet/bluff frequencies; likely structural, not just
a param tweak — trial 741 showed param-tuning alone didn't move it).
