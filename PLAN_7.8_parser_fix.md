# Skantbot 7.8 — Parser Fix & Range-Chart Recovery Plan

**Date:** 2026-05-23
**Status:** Plan agreed; 7.7 stays as ship-candidate until 7.8 passes locked gates.

---

## TL;DR of the bug

`_expand_to_freq_dict` in `bots/skantbot{7.4, 7, 7.7}/bot.py` parses hyphenated chart ranges (`"22-99"`, `"A2o-ATo"`) as HIGH→LOW. Charts are written LOW→HIGH. The reversed `range(hi_idx, lo_idx+1)` yields an empty iterator, the chart entry is silently dropped, and the try/except never fires (no exception is raised — Python's `range` is happy to return nothing).

**Charts affected** (identical breakage across 7.4, 7, 7.7):
- `HU_BB_CALL_FREQS`: 17 of 19 entries dropped → contains only `{87o, 76o}` instead of ~150 hands. This is the dominant leak.
- `THREEBET_CALL_FREQS[(BB, *)]` for all 6-max positions: 20/27/41/53 hands instead of ~80+
- `aggressor_likely_range`'s called-vs-our-3bet branch uses "99-22" (high→low) which accidentally works

**Why this explains everything we see:**
- vs tight openers (most field): we win 9000+ because `HU_BTN_OPEN_FREQS` works (opens 81%) and we steal blinds; the broken BB chart costs little because opponents rarely open
- vs aggressor (opens 70%): we fold 86% of BB defends → cede ~6000 chips/100h in uncontested BBs → barely break even
- The 7.4→7→7.7 trend (+2200 → +1157 → +112) is at most 1-2σ given HU bust variance — likely noise on top of a real baseline leak

**Empirical fix impact** (parser patched in diag bot, CRN compare vs stable 7.7, 100 seeds):
- **6-max (qualifier format)**: wins vs ALL 23 opponents, ~+1280/opponent/match averaged, several at 3σ+. Aggressor +2269 ± 834.
- **HU (Day 5 bracket)**: net-negative — regresses against polished bots (gemini-1 -2155, claude-4 -846, gemini-6 -830) because Optuna-tuned thresholds compensated for the broken charts.

---

## Step 0 — Targeted code audit (the user's "could there be more like this?" question)

Don't audit the whole bot. Audit the specific failure shape: **silent dataloss with no exception**.

### 0a. Chart-expansion audit
For every `_expand_to_freq_dict(...)` callsite in `bots/skantbot7.7/bot.py`:
- Dump `len(result)` at module load
- Anything with a multi-entry string that resolves to <5 hands is suspect
- Already-known offenders to verify cleared after fix: `HU_BB_CALL_FREQS`, `THREEBET_CALL_FREQS[("BB","LJ"|"HJ"|"CO"|"BTN")]`

Convert findings into **module-load startup assertions** in dev bot:
```python
assert len(HU_BB_CALL_FREQS) > 100, f"HU_BB_CALL_FREQS underpopulated: {len(HU_BB_CALL_FREQS)}"
assert len(THREEBET_CALL_FREQS[("BB","LJ")]) > 50, ...
# etc for each known-good size
```
If a future chart edit reintroduces the same shape of bug, it fails loudly at import instead of silently at runtime. Five lines of code, permanent guardrail.

### 0b. "Compute then silently use" audit
Audit these specific functions for paths that silently return empty/default:
- `aggressor_likely_range` — what if `_narrow_range` returns empty?
- `_narrow_range` — already has `subset if subset else rng_dict` fallback, OK
- `equity_vs_range` — what if `weighted_combos` is empty after filtering by `freq > 0`? Already falls back to `equity_vs_random`, but verify the fallback path is exercised correctly
- `_effective_freq` — multiplies several factors; check if any path can zero out a freq we wanted to preserve

For each: ask "if this returned a default/empty value, would the caller notice or just behave conservatively?" Conservative-silent = same shape as the parser bug.

### 0c. `range()` bounds from runtime data
Grep for any `range(` where the bounds are computed (not literal constants). The parser bug was `range(hi, lo+1)` with hi<lo silently empty. Look for the same pattern elsewhere.

**Audit scope: 1-2 hours max.** If it grows beyond that, surface findings to user and decide whether to proceed or expand scope.

### NOT in scope
- Postflop decision logic — bugs there raise exceptions, would show in our exception counter (already verified clean)
- Equity sims — same
- Opponent profile math — same

---

## Step 1 — Parser fix (in BOTH submission AND dev bots, in lockstep)

The fix:
```python
# Pocket pairs branch
elif "-" in part:
    bits = part.split("-")
    a = RANK_IDX[bits[0][0]]
    b = RANK_IDX[bits[1][0]]
    lo_i, hi_i = (a, b) if a <= b else (b, a)
    for i in range(lo_i, hi_i + 1):
        result[RANKS[i] + RANKS[i]] = freq

# Non-pairs branch
elif "-" in part[3:]:
    bits = part.split("-")
    a = RANK_IDX[bits[0][1]]
    b = RANK_IDX[bits[1][1]]
    lo_i, hi_i = (a, b) if a <= b else (b, a)
    for i in range(lo_i, hi_i + 1):
        result[r1 + RANKS[i] + suit] = freq
```

**Apply to:**
1. `bots/skantbot7.8/bot.py` (new copy of 7.7, then patched) — submission candidate
2. `harness/skantbot_dev/bot.py` AND `harness/skantbot_tunable/bot.py` — verify both have the same bug, patch in lockstep

If submission and dev bot diverge here, the sweep results don't transfer. Five-second check, but skipping it wastes a sweep cycle.

Run `python sandbox/validator.py bots/skantbot7.8/bot.py` to confirm validator passes.

---

## Step 2 — Heldout-only sanity check (before sweep)

Before spending compute on Optuna, do a sanity CRN compare:
- `bot_a = bots/skantbot7.8/bot.py` (parser-fixed, NOT re-tuned)
- `bot_b = bots/skantbot7.7/bot.py` (stable)
- Mode: 6-max, full TRAIN_EXPANDED pool, 200 seeds × 200 hands × 15 tables, ~30 min run

**Expected:** parser-fix wins across most opponents (we already saw this at 100 seeds; 200 seeds tightens SEs). If it doesn't replicate, something's wrong with the fix or the comparison harness — stop and investigate before sweep.

Also run the heldout-pool compare to check that the gain is real and not just train-pool overfitting.

---

## Step 3 — Full Optuna sweep with HU gate

The intuition: with correct charts, the optimal parameters are somewhere new in the search space, and that "somewhere new" should be at least as good as the broken-chart optimum (correct-chart strategies are a superset of broken-chart strategies — anything expressible under broken charts is also expressible under correct charts + tighter thresholds).

**Caveat:** Optuna is stochastic, not a proof. Budget generously and gate explicitly.

### Sweep config
- **Trials:** 2000-3000 (vs 1500 baseline) — extra cost is hours of compute; alternative is shipping something worse in HU
- **Objective:** primary = 6-max pool mean; secondary = HU-bracket-opponent mean (the polished bots: gemini-1, claude-4, gemini-6, chatgpt-12)
- **Workers:** 28
- **Seeds per trial:** 40
- **Storage:** `sqlite:///harness/results/skb78_parser_fix.db`

### Lock criteria (must pass ALL before shipping)
1. **6-max pool mean ≥ 7.7 baseline** (we expect this to be strongly positive given Step 2)
2. **6-max heldout mean ≥ 7.7 baseline within SE** (no overfitting)
3. **HU vs polished bots (gemini-1, claude-4, gemini-6) mean ≥ 7.7 baseline within SE** — explicitly do not accept a 2000-chip HU loss for 200-chip 6-max gain. Same Phase-2a style locked gate.
4. **HU vs min_raiser ≥ 7.7 baseline** — preserve the Phase 2a improvement
5. **Validator passes** (`python sandbox/validator.py`)

If gate 3 fails after the sweep budget exhausts:
- DO NOT ship
- Investigate: is the sweep finding the wrong tradeoff? Add HU bots to training pool with higher weight, re-sweep
- If still failing: accept that the parser fix may not be net-positive across both formats; reconsider 7.8 scope (e.g., ship parser fix as "6-max only" variant? probably not worth the complexity)

---

## Step 4 — Validation & ship

If all gates pass:
1. Tag `v7.8-stable` (7.7 stays as `v7.7-stable` for rollback)
2. Update `harness/opponents/registry.py:SKANTBOT_TUNABLE_PATH` to point at 7.8 dev variant
3. Update CLAUDE.md and memory notes to reflect 7.8 as ship candidate
4. Verify with `python -m harness.cli compare bots/skantbot7.8/bot.py bots/skantbot7.7/bot.py --mode 6max --seeds 200 --hands 200 --n-tables 15` one more time as a final check

---

## What this plan does NOT do

- Re-architect anything in the bot logic
- Touch postflop logic (it's working fine — exception counter showed clean)
- Touch opponent profile tracking (verified working at hand_complete)
- Attempt to manually rewrite chart strings to high→low (the parser fix is more robust — handles both directions)

---

## Risks & known unknowns

| Risk | Mitigation |
|---|---|
| Sweep can't find a config that beats 7.7 in HU | Gate 3 catches this; don't ship |
| Other silent-dataloss bugs discovered in audit | Surface immediately; expand scope or defer 7.8 |
| Parser fix changes range sizes enough to break CRN determinism check | Run `compare(path_X, path_X, pool)` self-test; must produce `paired_diff_mean == 0.0` per CLAUDE.md |
| Dev bot and submission bot drift | Step 1 explicitly patches both in lockstep |
| 6-max gain we measured (1280/opp/match) was noise from instrumentation differences | Step 2 replicates at higher seeds before committing to sweep |

---

## Estimated effort

- Step 0 (audit): 1-2 hours
- Step 1 (parser patch + validator): 30 min
- Step 2 (sanity compare): 30 min wall clock
- Step 3 (full sweep): 6-12 hours compute, 30 min hands-on
- Step 4 (ship): 30 min

Total wall: ~10-16 hours, mostly waiting on compute. Hands-on: ~3 hours.
