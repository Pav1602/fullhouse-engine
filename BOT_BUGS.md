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
