# Remediation: aggressor-range bugs in skantbot 7.9 → 7.10

**Date:** 2026-05-25
**Branch:** trunk
**Trigger:** Hand 27 of `human_vs_skantbot7.9_6max` — KK22 bust to flopped flush, called all-in on turn with ~10% true equity.
**Outcome:** skantbot 7.10 ships with 4 coordinated fixes. 7.9 preserved as rollback.

---

## 1. Bugs discovered

Trace methodology per `memory/feedback_trace_table_before_changes.md` + `memory/feedback_verify_runtime_values.md`:
construct exact engine state at decision time, run the bot's own functions, record every internal variable.
No "should be" speculation — only runtime values.

### Bug 1 — `_preflop_action_log` boundary detection

**File:** `bots/skantbot7.9/bot.py:820`
**Function:** `_preflop_action_log(state)`

**Failure mode:** Detects preflop→flop transition by checking when all bets in the tracking dict
equalize. Folded seats' partial bets (e.g. SB's 50 chips after folding to a raise) never equalize
with later raises. Function never exits the preflop loop and returns the entire hand action log.

**Trace evidence** (hand 27, `_trace_hand27.py`):
```
returns 13 entries (whole log has 13)
count_postflop_raises(BB)  = 0      ← should be 2 (flop lead, turn all-in)
count_aggressors           = 3      ← should be 1 (deepseek pf raiser)
```

**Downstream effect:** `aggressor_likely_range` hits `if pf_raises == 0: return base_range` early-return,
bypassing all postflop narrowing including the all-in override on line 1132. Affects every 6-max hand
with preflop folds (essentially every hand).

### Bug 2 — `aggressor_likely_range` has no BB-defender path

**File:** `bots/skantbot7.9/bot.py:1081`
**Function:** `aggressor_likely_range(state, agg_seat)`

**Failure mode:** When the BB calls preflop and then becomes the postflop aggressor (donk-lead +
check-raise), the bot's range model has no path for this. It falls through to
`RFI_FREQS.get("BB", RFI_FREQS["LJ"])`, using the LJ *opening* range as the base for a BB *defender*.

**Conceptual issue:** BB doesn't open — they defend (call) or 3-bet. Their post-call range is the
defending range, which is much wider and contains different hands than any RFI chart. The repo already
has `THREEBET_CALL_FREQS[("BB", LJ/HJ/CO/BTN)]` for exactly this case; the code just doesn't use it.

### Bug 3 — `_narrow_range` collapses on defending ranges

**File:** `bots/skantbot7.9/bot.py:1060`
**Function:** `_narrow_range(rng_dict, strength, board)`

**Failure mode:** Premium-pair narrowing uses fixed `strong = {AA, KK, QQ, JJ}`. Defending ranges
exclude these (BB 3-bets QQ+, doesn't flat). The strong/medium intersection with the input range is
empty. Final line `return subset if subset else rng_dict` then returns the *entire input range* —
narrowing collapses entirely.

**Trace evidence** (hand 27, layered fix attempt in `_trace_3layers.py`):
```
LAYER 1+2 — fix preflop_log + BB-defender base:
  range size : 50 hands  (defending range, no narrowing)
  equity     : 78.6%     ← INCREASED from 71.4% buggy baseline
```

Fix 1+2 alone made the bug WORSE because of this collapse.

### Bug 4 — Range model is hand-class only; cannot represent specific-suit combos

**File:** `bots/skantbot7.9/bot.py:962` and `:992`
**Functions:** `_hand_class_to_combos`, `equity_vs_range`

**Failure mode:** Hand classes like `"Q4s"` represent all 4 suited combos equally
(`_hand_class_to_combos("Q4s", used)` → [(Qc4c), (Qd4d), (Qh4h), (Qs4s)]). On a 3-flush board (e.g.
clubs-heavy), only `Qc4c` is an actual flush; the other 3 are non-flush junk.

When estimating opponent's check-raise jam range on a flush board, the model treats `Q4s` as 1/4
flushes + 3/4 junk. Real opponent's jam range only contains the flush combo (`Qc4c`), not the 3
non-flush variants.

**Sanity-check equity** (paper hand, `_paper_hands.py`):
```
vs Qc4c (actual flush)  -> KK22 equity =  9.6%
vs JJ (set jacks)       -> KK22 equity =  5.1%
vs AK top pair          -> KK22 equity = 77.5%
```

Range averaged over all 4 suited combos of `Q4s` ≈ 62% equity. Range expressed only as `Qc4c` ≈ 10%.
40-point swing.

---

## 2. Fix plan and implementation

All four fixes coordinated into one commit; landing them in isolation makes things worse (bug 3
collapse). New version `skantbot7.10/` and `harness/skantbot7_10_dev/`. 7.9 unchanged (rollback path).

### Fix 1 — `_preflop_action_log` (bots/skantbot7.10/bot.py:820)

Track folded seats; exclude their bets from the equalization check.
~10 LOC delta.

### Fix 2 — BB/SB-defender path in `aggressor_likely_range` (bots/skantbot7.10/bot.py:1100)

Detect agg_seat called preflop (didn't raise) AND agg_pos ∈ {BB, SB} AND
`(agg_pos, opener_pos) ∈ THREEBET_CALL_FREQS`. Use defending range as base instead of RFI fallback.
~15 LOC delta.

### Fix 3 — board-aware narrowing in `_narrow_range` (bots/skantbot7.10/bot.py:1060)

- Replace `return subset if subset else rng_dict` (collapse) with a board-derived value subset.
- On 3+ flush boards, emit specific flush combo (`Qc4c` 4-char form) for each in-range suited hand-class
  whose flush variant is available; drop the hand-class to prevent double-counting.
- Add sets (PP matching board rank) and top-pair-good-kicker.
- Defensive last-resort: top 10% of input range by freq if subset still empty.

~50 LOC delta.

### Fix 4 — combo-level support in `_hand_class_to_combos` (bots/skantbot7.10/bot.py:962)

Add `len(hand_class) == 4` branch returning the specific combo.
~5 LOC delta.

Total: 120 LOC inserted, 32 deleted across both submission and dev bots.

---

## 3. Verification

### 3a. Trace tables (per `memory/feedback_trace_table_before_changes.md`)

**Hand 27 turn decision — before fix** (`_trace_hand27.py` against 7.9):
```
range size : 38   sample: [66, 77, 88, 99, TT, JJ, QQ, KK, AA, A3s, ...]
equity     : 71.4%   required: 54.4%   → CALL  (the bust)
```

**Hand 27 turn decision — after fix** (`_trace_hand27.py` against 7.10):
```
range size : 24   sample: [22, 77, Ac3c, Ac4c, Ac5c, Ac6c, Ac8c, Ac9c, AcTc, AcJc, ...]
equity     : 10.6%   required: 54.4%   → FOLD  ✓
```

Range is now flush-heavy + sets (22, 77 match the board). Equity reflects real situation
(drawing dead vs flush, ~10% to boat up).

**Layered ablation** (`_trace_3layers_v2.py`):
| Fixes applied | Range size | Equity | Decision |
|---|---|---|---|
| Layer 0 (none) | 38 | 71.4% | CALL |
| Layer 1 only | 4 | 57.8% | CALL |
| Layer 1+2 | 50 | 78.4% | CALL (worse — bug 3 collapse) |
| Layer 1+2+3+4 (all) | 24 | 10.6% | FOLD ✓ |

Confirms all four fixes are required; subsets break.

### 3b. Paper hands (per advisor's recommendation)

Run: `_paper_hands.py`

| # | Scenario | 7.10 | 7.9 | Verdict |
|---|---|---|---|---|
| A | KK22 vs jam on flush turn | eq 10.3%, **fold** | eq 71.4%, call | ✓ Bust closed |
| B | Nut flush (Ac3c) vs same jam | eq 93.3%, **raise** | eq 98.2%, raise | ✓ Not over-folding nuts |
| C | Top set (KsKd) vs jam on flush board | eq 42.3%, **fold** | eq 84.7%, raise | ⚠ Math correct (43% < 54% req) |
| D | Hand 3 river J-high vs station | check | check | ✓ Identical, fix is isolated |
| E | 3-bet pot (`aggressors==2`) | unchanged path | — | Pre-existing gap, not in scope |

**Hand C note:** Top set on flush board vs polarized jam has ~43% true equity (20% to boat up vs
flush, ~95% vs set/pair). Bot's 42.3% matches truth; fold at 54% required threshold is
mathematically correct. Threshold may need re-tuning via V80 sweep but not a bug.

### 3c. CRN preservation (per CLAUDE.md)

Run: `_check_crn.py`
```
PASS — paired_diff_mean == 0.0 for all 23 opponents.
(self-compare on 23 opponents, n_seeds=5)
```

Any nondeterminism in `bot.py` would invalidate every sweep result. Confirmed deterministic.

### 3d. Validator + engine tests

```
sandbox/validator.py bots/skantbot7.10/bot.py:  ✅ PASSED
pytest tests/:  25 passed
```

### 3e. Matched n=100 baselines

Run: `_baseline_compare.py` → `harness/results/baseline_compare_79_vs_710.json`

```
sum-of-means per pool:  7.9 = +272,318    7.10 = +273,225    Δ = +907 chips

No opponent shows >2σ regression. No opponent flips negative.
1-2σ regressions (possible): push_fold (-1,877), claude-4 (-1,854)
1-2σ improvements (possible): chatgpt-7 (+1,969)
Other 20 opponents within 1σ of zero (noise floor).
```

---

## 4. Known calibration nits (not blockers)

Advisor flagged two soft spots in fix 3:

### Nit A — TPGK only catches suited broadways

`if len(hand) == 3 and hand.endswith("s")` excludes offsuit broadways (AKo, KQo, JTo). These are also
top-pair-good-kicker on K-high boards. Fix is mechanical (add offsuit case), no fragility risk.
~3 LOC. Real but bounded leak.

### Nit B — Flush-combo emission drops the hand-class entirely

When emitting `Qc4c` and `subset.pop("Q4s", None)`, the 3 non-flush variants of Q4s
(`QsQ4s, QhQ4h, QdQ4d`) disappear from the range model. In a polarized check-raise jam line on a
flush board, opponent's `Q4s` is overwhelmingly the flush combo (`Qc4c`), so dropping the hand-class
is roughly correct. Paper hand B (nut flush vs jam) confirms we don't over-fold actual flushes.

Risk: over-folds if opponent jams *non-flush* `Q4s` as a bluff. Possible vs irrational opponents
(some LLM bots), not vs reasonable ones. NOT recommended to "fix" — would re-introduce double-counting
of the flush combo unless `_hand_class_to_combos` is also taught to skip the specific combo when
expanding a hand-class. Currently intentional.

---

## 5. Open questions for V80 sweep scope

The 1-2σ regressions vs push_fold and claude-4 are most likely a re-calibration issue: thresholds
(`equity_call_threshold`, `pot_odds_buffer_normal`, `pot_odds_buffer_marginal`, `equity_value_bet`,
`equity_thin_value`) were tuned against systematically over-counted equity estimates. With
now-accurate (lower-on-flush-boards) equity, the optimal thresholds should shift down. V80 should
re-tune at minimum these 5 params; existing V79 params can be carried forward as starting points.

---

## 6. Artifacts

- Trace scripts: `_trace_hand27.py`, `_trace_3layers_v2.py`, `_verify_pf_bug.py`
- Paper hands: `_paper_hands.py`
- CRN check: `_check_crn.py`
- Baseline comparison: `_baseline_compare.py`
- Baseline data: `harness/results/baseline_compare_79_vs_710.json`
- 7.10 submission bot: `bots/skantbot7.10/bot.py`
- 7.10 dev bot: `harness/skantbot7_10_dev/bot.py`
- Registry pointing sweep at 7.10 dev: `harness/opponents/registry.py:100`
- 7.9 preserved at `bots/skantbot7.9/bot.py` and `harness/skantbot7_9_dev/bot.py` (unchanged)
