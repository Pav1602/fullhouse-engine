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
