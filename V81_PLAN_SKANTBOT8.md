# V81 Plan — skantbot8

This document is the complete context window for the agent implementing
skantbot8. Read it end-to-end before starting. Every recommendation here
came from the V80b cycle's mistakes — don't repeat them.

## 0. Why this document exists

V80b ran a 60-param Optuna sweep, found train-improving candidates, all of
which catastrophically overfit the heldout pool (best candidate #189 lost
σ=+9.29 to 7.13 on heldout). A surgical attempt (7.14 with a donk-lead
guard) also failed (heldout σ=+5.77 vs 7.9). After the cycle, 1D
parameter sweeps + action-distribution analysis confirmed Pareto
saturation: 7.13's structural fixes are already at a local frontier
between bust prevention and routine chip yield. No simple parametric or
single-branch surgical fix can break the coupling.

skantbot8 must break the coupling **structurally** — by changing the
*logic* of decision-making, not just the parameters. Four changes are
planned (numbered as in original V81 brief):

- **#4 Pool rebalance** (operational, do first)
- **#1 Bet-sizing signal in range narrowing** (structural, low risk)
- **#2 Per-opponent range narrowing** (structural, medium risk)
- **#5 Forward-looking call decisions** (structural, high risk)
- **V81 sweep** (after #1, #2, #5 individually verified)

Deferred to V82: #3 (calibrated equity model) — it's a research project
that touches CRN; high risk for sweep integration.

## 1. What 7.13 is and what skantbot8 must preserve

**7.13 is committed at `aad7256`, tagged `v7.13-stable`.** It is the
tournament submission. Files:

- `bots/skantbot7.13/bot.py` — submission (NO `import os`, validator-clean)
- `harness/skantbot7_13_dev/bot.py` — dev variant with env-driven Config
  loading + `reset_match_state()` + `set_config_from_dict()` for in-process
  worker use

7.13 closed two structural HU preflop bugs:
1. `aggressors==1` was overloaded between "BB defends" and "SB faces 3-bet"
   — used the wrong chart for the latter; A4o called 3-bets at 100%
2. `aggressors==2` was overloaded — sized partial 5-bets via `fourbet_size_ip`
   instead of going all-in-or-fold

skantbot8 changes must preserve:
- All of 7.13's structural fixes (do NOT undo the HU dispatch fix, the
  3-bettor branch, the A-low-low texture change, etc.)
- min_raiser HU ≥ +3000 chips/match (gate)
- CRN: `paired_diff_mean == 0.0` on self-compare across all 23 train opps
- Validator clean on submission bot
- 25/25 unit tests pass

**Hard rule: every change gets a gate check after implementation. If
ANY gate fails, the change is rolled back.**

## 2. Lessons from V80b — do not repeat

### Lesson 1 — Train/heldout pool design is the dominant factor

V80b's failure was not the sweep design alone; the train pool was
LLM-dominated (claude-2/4/7/11/12, gemini-1/6/11, grok-3, chatgpt-2/7/12,
deepseek-5, mathematician, plus a few mid-pool archetypes) and the
heldout pool was archetype-dominated (super_nit, fit_or_fold,
maniac_aggro, limp_machine, claude-9, deepseek-10, grok-8). Any TPE
optimization on train pushed AWAY from heldout. **Pool rebalance (#4) is
mandatory before any sweep.**

### Lesson 2 — Multi-objective Pareto front lets train_mean dominate

V80b used 3-objective Pareto (train_mean, train_worst, unseen_mean). TPE
found train-improving candidates that were Pareto-optimal but had small
unseen losses that turned out to be huge in real evaluation. **V81 uses
a single weighted scalar objective** that forces train+heldout balance:

```
score = 0.4 × train_mean + 0.6 × min(per_opp_chip_delta on heldout)
```

The `min` instead of `mean` is critical — it forces TPE to find solutions
where NO heldout opp regresses badly.

### Lesson 3 — 60-dim space + 1110 trials = chasing noise

V80b had ~18 trials per dim. TPE rule of thumb is 50-100 per dim. V81
uses ~15 focused params (only the ones with theoretical motivation AND
1D-sweep evidence), 2000 trials → ~130 trials/dim.

### Lesson 4 — Sweep "unseen_mean" tracking is statistically weak

V80b's reported unseen_mean for trial #189 was -198 chips/opp; reality
was -1400/opp. With small n_seeds in the unseen evaluation phase, the SE
swamps the signal. V81 must use ≥30 seeds for ANY metric the objective
depends on, AND verify the post-sweep best trial with INDEPENDENT runs
at ≥30 seeds before declaring it a candidate.

### Lesson 5 — Speculative surgical fixes without tracing fail

The 7.14 donk-lead-guard was proposed without first reproducing the
specific bust pattern. When traced, the donk-lead-3-streets pattern
turned out to be a ~4% probabilistic bluff-barrel roll, not deterministic
behavior. The guard intercepted legitimate value bets more than it
intercepted bluff cascades. **Every structural change in V81 must be
preceded by trace tables proving the hypothesized behavior actually
occurs in the targeted decision paths.**

## 3. Pre-work (do this first, before any structural change)

### 3.1 Build the diagnostic toolkit (~half day)

Four scripts you'll reuse across every step. Build them all FIRST so you
don't conflate "validation isn't working" with "the change doesn't work."

**3.1a — `_pool_signature.py`**

For each opp in train + heldout, compute behavioral signature: avg VPIP,
avg PFR, avg aggression factor, avg fold-to-cbet (dry vs wet), avg WTSD.
Plot train vs heldout as 2D PCA or just side-by-side histograms.

Output: pickled signature table + matplotlib plot. The plot should make
it visually obvious whether train and heldout are separable clusters.

**3.1b — `_eq_calibration.py`**

Run 7.13 against a small fixed pool for ~1000 hands. At each
postflop decision point, log `(estimated_eq, opp_actual_hand_eq)` —
where opp_actual_hand_eq comes from seeing the opp's revealed cards at
showdown (or from a forward sim if no showdown).

Per opp class (nit / station / maniac / LLM), compute:
- Mean calibration error (estimated_eq - actual_eq)
- Stdev of error

Use this as the baseline. After each change, re-run on the same fixed
seed to see if calibration error decreased per opp class.

**3.1c — `_range_unit_test.py`**

For a fixed set of 20 (state, agg_seat) combinations covering:
- Preflop 3-bet pots (BB vs BTN, SB vs CO, etc.)
- Postflop dry/wet/medium boards
- 1, 2, 3 postflop raises
- Different aggressor profiles

Compute `aggressor_likely_range(state, agg_seat)` size + hand
composition. Report as a fixed table. Run before and after any change to
the range narrowing logic; the diff is the proof of behavior change.

**3.1d — `_paired_bust_diff.py`**

Take two bot versions A and B. Run both against the same opponent pool
+ same seeds. For each (seed, opp_set), measure:
- chip_delta_A vs chip_delta_B
- bust counts per family per bot

Output: per-family bust count and dollar diff with statistical
significance. This replaces running two separate bust surveys (which
can't be directly compared because they use different seeds).

**Acceptance criteria for the toolkit**: each script runs without error
and produces sensible output for the 7.13 baseline (e.g., calibration
error is non-zero but reasonable, range sizes vary across states, pool
signatures show measurable differences).

### 3.2 Confirm pool bias hypothesis (~30 min)

Run `_pool_signature.py` on current train + heldout. Visual check:
- Are train and heldout in different regions of the feature space?
- Is there variance WITHIN each pool (multiple distinct types) or are
  they each tight clusters?

**Go/no-go criterion**: if train and heldout are clearly separated
(e.g., heldout's median aggression factor is >2x train's or similar
strong signature), the pool bias hypothesis is confirmed and #4 has
high expected value. If they overlap significantly, the bias is
secondary; the structural changes are the only lever, and you should
also consider that V80b might have failed for a different reason.

This 30-minute check determines whether the full plan proceeds OR needs
revision.

## 4. Step 1 — Pool rebalance (#4) — half day

**Goal**: train and heldout pools have similar behavioral distributions
so any train optimization transfers.

### 4.1 Pre-diagnostic (do first, ~20 min)

Use `_pool_signature.py` output from 3.2. Identify:
- Which 2-3 archetypes in heldout are most "archetype-like" (low VPIP,
  unusual aggression patterns) — these should be moved TO train
- Which 2-3 train bots are most "archetype-like" — should STAY in train
- Which 2-3 train bots are most "median LLM" (claude-4, gemini-1, etc.)
  — move TO heldout

Goal: post-move, each pool should have at least 1 representative of each
behavior cluster.

### 4.2 Implementation

Modify `harness/opponents/registry.py`:
```python
# V81 pool design: stratified by behavioral cluster
_ARCHETYPES_TRAIN_V81 = _ARCHETYPES_TRAIN | {
    "super_nit": "harness/opponents/.../super_nit/bot.py",
    "fit_or_fold": "harness/opponents/.../fit_or_fold/bot.py",
    "maniac_aggro": "harness/opponents/.../maniac_aggro/bot.py",
}
# Move 2-3 LLMs to heldout
_HELDOUT_V81 = {
    # Keep some archetype diversity in heldout
    "limp_machine": "...",
    "claude-9": "...",
    "deepseek-10": "...",
    # Plus newly-moved LLMs
    "claude-4": "harness/opponents/.../claude-4/bot.py",  # moved from train
    "gemini-1": "harness/opponents/.../gemini-1/bot.py",  # moved from train
    "chatgpt-2": "harness/opponents/.../chatgpt-2/bot.py", # moved from train
}
TRAIN_EXPANDED_V81 = ...
UNSEEN_VALIDATION_V81 = _HELDOUT_V81
```

**Critical**: Keep `TRAIN_EXPANDED` and `UNSEEN_VALIDATION` unchanged for
back-compat with the 7.13 verification scripts. Add NEW names `*_V81`.
Use the new names only in the V81 sweep config + V81 verification.

### 4.3 Validation gate

**Diagnostic**: re-run V80b's trial #189 verification against the NEW
rebalanced pool. The exact command:

```python
# Extract trial 189 params (same as in V80b cycle)
# Build 7.14_trial189 (or load from existing bots/skantbot7.14/)
# Run paired-diff vs 7.13 on TRAIN_EXPANDED_V81 + UNSEEN_VALIDATION_V81
```

Three possible outcomes:

- **Outcome A: trial #189 still overfits by σ > +5 on heldout** → pool
  design wasn't the dominant issue. Pool rebalance is partial help only.
  Structural changes still mandatory.
- **Outcome B: trial #189 overfits by σ < +3 on heldout** → pool was a
  contributor but other things matter. Proceed with structural changes
  as planned.
- **Outcome C: trial #189 no longer overfits** → pool was the dominant
  cause. Structural changes #1/#2/#5 may not be necessary. Consider
  running V80c sweep on the rebalanced pool first.

Record which outcome you got. The downstream plan depends on it.

### 4.4 Commit + tag

```
git add harness/opponents/registry.py
git commit -m "V81: pool rebalance — TRAIN_EXPANDED_V81 + UNSEEN_VALIDATION_V81"
git tag v81-step4-pool-rebalance
```

## 5. Step 2 — Bet-sizing signal in range narrowing (#1) — 1 day

**Goal**: `aggressor_likely_range` narrows based on opp's BET-SIZING (not
just raise count), so commitment-tier bets immediately collapse the
range to value-only.

### 5.1 Pre-diagnostic (do first, ~1 hour) — MANDATORY

This is where the 7.14 attempt failed. Don't skip.

Pick 50 bust hands from 7.13's heldout bust survey
(`harness/results/bust_survey_skantbot7.13_heldout_n100.json`). For each:

1. Trace the bot's decisions using `_trace_bust_036.py`-style replay
   (file already exists from V80b cycle — adapt for the specific hand_id)
2. At each decision where the bot lost chips, record:
   - The actual opp's last bet's `(amount, pot_before)` ratio
   - Whether the bot's `aggressor_likely_range` at that point was
     "too wide" (>10 hands) when the bet ratio was ≥0.75 (commitment-tier)
3. Aggregate: what % of bust scenarios show the signal? (i.e., bet/pot ≥
   0.75 AND range was wider than nuts-only)

**Acceptance criterion**: if ≥40% of bust scenarios show the signal,
the fix has real reach. If <20%, the leak is elsewhere and #1 won't help
much.

If <20%: STOP. Re-investigate before implementing. Probably means
the busts are from different patterns than expected.

### 5.2 Trace table requirement

Before writing the implementation, build a trace table for 3 specific
decision states:

| State | Current `aggressor_likely_range` | Proposed (with #1) | Why different |
|---|---|---|---|
| Flop, opp bet 50% pot | medium tier (~13 hands) | medium tier (~13 hands) | Below 0.75 → no change |
| Flop, opp bet 100% pot | medium tier (~13 hands) | **strong tier (~6 hands)** | Above 0.75 → tier up |
| Turn, opp jam (overbet) | strong tier (already) | strong tier (already) | Already at top tier |

Document the expected eq change (Monte Carlo sim, 300 iterations) for
your A4 hand vs each range:
- Current: ~0.35 vs medium
- Proposed: ~0.20 vs strong
- Decision change: call → fold (assuming required_eq ~0.30)

Show this table BEFORE writing code. If you can't predict the behavior,
you don't understand the change.

### 5.3 Implementation

In `bots/skantbot8/bot.py` and `harness/skantbot8_dev/bot.py`:

```python
# In aggressor_likely_range(), after computing 'strength' from pf_raises:

# Add: bet-sizing signal overrides raise count for commitment-tier
postflop_log = state.get("action_log", [])[len(_preflop_action_log(state)):]
last_raise = next((e for e in reversed(postflop_log)
                   if e.get("action") in ("raise", "all_in")
                   and e.get("seat") == agg_seat), None)
if last_raise:
    # Compute pot before the raise
    log_idx = postflop_log.index(last_raise)
    pot_before_raise = pot - sum(e.get("amount", 0) for e in postflop_log[log_idx:])
    if pot_before_raise > 0:
        bet_to_pot = last_raise.get("amount", 0) / pot_before_raise
        if bet_to_pot >= 0.75 and strength != "strong":
            strength = "strong"
```

Place this between the existing `strength = "medium"` assignment and the
`if _aggressor_last_action_is_allin` block.

Make BOTH bot files identical except for the env-var loading at the top
of the dev variant.

### 5.4 Paper hand verification (do BEFORE running CRN/gates)

Build `_paper_hands_skb8_step1.py`:

```python
# For each of 5 hand scenarios, replay the bot decision with both
# 7.13 and skantbot8. Confirm the action change matches the trace table.
SCENARIOS = [
    {"label": "A4 vs nit bet 100% pot", "expect_7_13": "call", "expect_skb8": "fold"},
    {"label": "A4 vs nit bet 40% pot",  "expect_7_13": "call", "expect_skb8": "call"},  # signal doesn't fire
    {"label": "AK vs nit bet 100% pot", "expect_7_13": "call", "expect_skb8": "call"},  # high eq still
    {"label": "76s vs maniac bet 100%", "expect_7_13": "fold", "expect_skb8": "fold"},  # no change
    {"label": "TT vs nit overbet jam",  "expect_7_13": "fold", "expect_skb8": "fold"},  # no change
]
```

Acceptance: 5/5 match expectations. If any don't, the implementation
diverges from the design — fix before proceeding.

### 5.5 Validation gates

In strict order. Stop if any fails.

**Gate A — Validator + tests + CRN**
- `python sandbox/validator.py bots/skantbot8/bot.py` → PASS
- `python -m pytest tests/` → 25/25
- `python _check_crn.py` → `paired_diff_mean == 0.0` for all train opps

**Gate B — min_raiser HU preservation**
- `python _check_min_raiser_skb8.py` (adapt from existing
  `_check_min_raiser_714.py`) → skantbot8 vs min_raiser HU ≥ +5000 chips
- If +5000 to +5400: PASS, marginal — note for monitoring
- If <+5000: FAIL, the signal misfired against min-raiser's small bets

**Gate C — Bust survey: hero-call class doesn't grow**
- Run `_bust_survey_param.py` on skantbot8 vs train + heldout (both)
- Run `_paired_bust_diff.py` comparing skantbot8 vs 7.13 on same seeds
- Hero-call late street family: skantbot8 must NOT be >7.13 by more
  than 5% on either pool

**Gate D — Paired-diff vs 7.13 on rebalanced pools**
- skantbot8 vs 7.13 on TRAIN_EXPANDED_V81: net positive (Δ < 0 in
  "a - b = baseline - new" convention; magnitude > 100 chips/opp)
- skantbot8 vs 7.13 on UNSEEN_VALIDATION_V81: net positive OR no >2σ
  regression on any single opp

**Gate E — Paired-diff vs 7.9 on rebalanced pools**
- Same standard as Gate D

If all gates pass: commit as `v81-step1-bet-sizing`. If any fail: roll
back, re-trace, fix root cause, re-test.

## 6. Step 3 — Per-opponent range narrowing (#2) — 1 day

**Goal**: narrowing intensity scales with opp's classification:
- nits (low aggression_factor) → narrow MORE
- maniacs (high aggression_factor) → narrow LESS
- unknown opps → use current 7.13 behavior

Depends on #1 (modifier applies on top of bet-sizing signal).

### 6.1 Pre-diagnostic (do first, ~30 min) — MANDATORY

Verify the bot's opp_profile has enough fidelity to differentiate:

1. Run a 400-hand match vs super_nit. After the match, log
   `super_nit_profile.aggression_factor`, `vpip`, `hands_observed`.
2. Same for maniac_aggro, calling_station, claude-4.
3. Confirm the values are MEANINGFULLY different (e.g.,
   super_nit AF < 0.5, maniac_aggro AF > 1.5).

If they're all in [0.7, 1.3] (i.e., classification doesn't distinguish
them), the per-opp modifier has nothing to work with. STOP and either:
- Improve opp_profile (more aggressive classification, more axes)
- Or skip #2, go straight to #5

If they're clearly distinguishable: proceed.

### 6.2 Trace table requirement

For each opp class (nit / median / maniac) × each base strength (thin /
medium / strong), compute the proposed effective strength tier:

| Opp class | nit (AF<0.5) | median (0.7≤AF≤1.3) | maniac (AF>1.5) |
|---|---|---|---|
| Base = "thin"   | medium | thin   | thin |
| Base = "medium" | strong | medium | thin |
| Base = "strong" | strong | strong | medium |

Then for one scenario per cell, predict the expected eq for a marginal
hand (e.g., A4 on dynamic board) vs each range. Confirm:
- vs nits: eq drops MORE than baseline → fold more
- vs maniacs: eq is closer to baseline → call more

### 6.3 Implementation

In `aggressor_likely_range`, after the bet-sizing logic from #1:

```python
if opp_profile and opp_profile.hands_observed >= cfg.min_hands_for_exploit:
    af = opp_profile.aggression_factor
    if af < 0.5:  # nit: narrow harder
        strength_tiers = {"thin": "medium", "medium": "strong", "strong": "strong"}
        strength = strength_tiers.get(strength, strength)
    elif af > 1.5:  # maniac: narrow softer
        strength_tiers = {"thin": "thin", "medium": "thin", "strong": "medium"}
        strength = strength_tiers.get(strength, strength)
```

### 6.4 Paper hand verification

Build `_paper_hands_skb8_step2.py` testing 6 scenarios (3 opp classes ×
2 base strengths). Confirm each strength tier shift is as predicted.

### 6.5 Validation gates

Same A-E as Step 2, plus:

**Gate F — Per-opp specific preservation**
- skantbot8 vs maniac_aggro HU: must not drop > 500 chips/match vs 7.13
  (over-narrowing here would be the failure mode)
- skantbot8 vs super_nit HU: must not drop > 500 chips/match vs 7.13
  (the opposite failure mode — over-loosening vs nits)
- If either drops > 500: the classification thresholds (0.5, 1.5) are
  wrong. Try (0.7, 1.3) and re-run. If still wrong, the per-opp
  modifier interacts badly with #1; investigate which is the root cause.

Commit as `v81-step2-per-opp-narrowing` if all gates pass.

## 7. Step 4 — Forward-looking call decisions (#5) — 2 days — HIGH RISK

**Goal**: when deciding to call a postflop bet, model the EXPECTED TOTAL
CHIPS we'll commit if we call (assuming opp's likely action line) vs
expected wins. Fold flop/turn when the cascade is -EV even if current
pot odds are met.

This is the LEAST safe change. Read this section twice before starting.

### 7.1 Pre-diagnostic (do first, ~2 hours) — MANDATORY

Three checks, all required:

**7.1a — Latency**

Sketch the forward-sim algorithm. Time a worst-case decision (e.g., 4
remaining decisions per street × 4 streets remaining = 16 sub-decisions
to simulate) on the dev machine. Must complete in <500ms (allowing
1.5s budget for the rest of decide()).

If the naive forward sim is too slow, you need either:
- Precomputed action-line tables per opp class
- Truncated horizon (just turn + river, not 4 streets ahead)
- Or skip #5 entirely

**7.1b — Verify the leak target exists**

Re-run the river_fold_after_invest count on 7.13's heldout. Confirm:
- ≥25 of these busts still exist (sample for V81 verification)
- The pattern is "skant invested ≥$2k, folded river to bet ≥$3k"

**7.1c — Verify forward-look would help**

Pick 5 specific river_fold_after_invest busts. Manually compute, for
each, what the bot's expected total cost would have been if it had
known opp's likely action line. Confirm:
- The expected cost > what 7.13 actually paid
- → forward-look would say "fold flop" earlier

If <60% of the 5 hands match this pattern, the leak isn't from
"shortsighted call decisions" and #5 won't help. Re-investigate.

### 7.2 Trace table requirement

For 3 specific decision states (flop call, turn call, river call),
document:

| State | Current logic | Forward-look logic | Predicted action change |
|---|---|---|---|
| Flop call, eq=0.45 vs nit, pot=$2k, opp's likely action line costs another $4k | call (eq > pot_odds) | fold (expected $6k cost, expected eq decay to 0.25 by river) | call → fold |
| Turn call, eq=0.5 vs maniac, pot=$3k, opp's likely cost $2k | call | call (expected $5k cost, expected eq 0.4 — still profitable) | no change |
| River call, eq=0.4 vs nit jam | fold (eq < required) | fold | no change |

### 7.3 Implementation

Pseudo-code (the next agent will need to fill in opp-class action-line
tables):

```python
# In decide_postflop, after computing eq, BEFORE the standard "if eq >= required_eq" call check:
if owed > 0 and street in ("flop", "turn"):
    expected_total_cost = _expected_remaining_cost_to_showdown(
        state, opp_class, eq, street
    )
    expected_total_win = ...  # eq * (pot + expected_total_cost)
    if expected_total_cost > expected_total_win + 200:
        # The cascade is -EV; fold even though current pot odds met
        return {"action": "fold"}
```

Where `_expected_remaining_cost_to_showdown` looks up opp_class's
typical (bet_freq, bet_size) per remaining street.

### 7.4 Paper hand verification

Build `_paper_hands_skb8_step5.py` testing 8 scenarios (call decisions
across flop/turn × nit/maniac/LLM × ahead/marginal). Confirm forward
logic produces the predicted actions.

### 7.5 Validation gates

Same A-F as Step 3, plus:

**Gate G — river_fold_after_invest drops on heldout**
- Run bust survey on skantbot8 with #1+#2+#5 active.
- river_fold_after_invest family must drop by ≥30% vs 7.13.
- If <15% drop: forward-look isn't catching the targeted leak. Re-test
  the action-line tables.

**Gate H — Hero-call doesn't regress**
- leak_called_with_weak_hand_late_street must NOT grow by more than 10%
  vs 7.13 on either pool.

**Gate I — Latency budget on real matches**
- Run 20 full 200-hand matches on the dev machine. Maximum single
  decision time should be < 1.8s. Average < 0.3s.

If all gates pass: commit as `v81-step5-forward-look`. This is the
biggest single risk — be paranoid.

## 8. Step 5 — V81 sweep — 1 day

After #1+#2+#5 are individually verified and stacked, run the sweep.

### 8.1 Param space (~15 params, focused)

```python
PARAM_SPACE_V81 = {
    # Confirmed-direction params from V80b 1D sweeps
    "equity_call_threshold":     ("float", 0.35, 0.50),
    "pot_odds_buffer_normal":    ("float", 0.08, 0.18),
    "equity_thin_value":         ("float", 0.40, 0.55),
    "bluff_freq_ip":             ("float", 0.01, 0.06),
    "bluff_freq_oop":            ("float", 0.01, 0.05),
    "cbet_freq_base":            ("float", 0.50, 0.70),
    "threebet_call_threshold_pct":("float", 0.10, 0.22),
    "fourbet_call_threshold_pct":("float", 0.08, 0.14),
    "fourbet_bluff_freq":        ("float", 0.05, 0.30),
    "k_commit":                  ("float", 0.0, 0.012),
    "river_v2b_half_pot":        ("float", 1.5, 3.0),
    "river_v2b_pot_sized":       ("float", 0.7, 1.6),
    # NEW from V81 structural changes
    "bet_to_pot_commit_threshold": ("float", 0.65, 0.90),  # from #1
    "narrowing_nit_modifier":    ("float", 1.2, 1.8),       # from #2
    "narrowing_maniac_modifier": ("float", 0.4, 0.8),       # from #2
    "forward_cost_buffer":       ("float", 100, 500),       # from #5 (chips margin)
}
```

### 8.2 Objective

**Single weighted scalar.** Not Pareto.

```python
def objective_v81(trial):
    train_results = compare(..., opponent_pool=TRAIN_EXPANDED_V81, n_seeds=30, ...)
    train_mean = sum(s["a_mean"] for s in train_results.values()) / len(train_results)

    heldout_results = compare(..., opponent_pool=UNSEEN_VALIDATION_V81, n_seeds=30, ...)
    heldout_per_opp = [s["a_mean"] for s in heldout_results.values()]
    heldout_min = min(heldout_per_opp)  # WORST opp, not mean

    return 0.4 * train_mean + 0.6 * heldout_min
```

The `min` over heldout opps forces TPE to find solutions where NO opp
regresses badly. Trial #189 from V80b would have scored terribly.

### 8.3 Sampler + trial budget

- Sampler: `optuna.samplers.TPESampler(seed=42)` (single-objective)
- Trials: 2000
- Anchor: enqueue current 7.13 + #1 + #2 + #5 defaults as trial 0
- Pool: TRAIN_EXPANDED_V81 + UNSEEN_VALIDATION_V81 (rebalanced)
- ETA on c7i.48xlarge spot: ~6 hours
- Cost: ~$12

### 8.4 Post-sweep verification (same 8 gates as 7.14)

After best trial extraction:
- Gates A through I from steps 2-4 above
- Add: independent paired-diff with n=40 seeds (not n=20 sweep evals)
  to verify the signal holds

If best trial passes all gates → ship as skantbot8.0.
If fails → ship 7.13 + #1 + #2 + #5 (without sweep params).

## 9. Engineering hygiene rules

Read these before EVERY commit.

### 9.1 Version preservation

- 7.13 MUST stay untouched. `bots/skantbot7.13/bot.py` and
  `harness/skantbot7_13_dev/bot.py` are sacred.
- skantbot8 work in `bots/skantbot8/` and `harness/skantbot8_dev/`
- DELETE the failed 7.14/7.14b artifacts ONLY after confirming v81-step1
  passes gates (in case you need to reference the failed approach)

### 9.2 CRN preservation — non-negotiable

After every code change to bot.py: `python _check_crn.py` must return:
```
PASS — paired_diff_mean == 0.0 for all 23 opponents.
```

If it doesn't: you introduced nondeterminism. Common causes:
- Unseeded `random.random()` instead of `rng = get_hand_rng(state)`
- Dict iteration order dependence (use sorted keys)
- Wall-clock branches (`time.time()` in decision logic)
- Floating-point reordering (sum order matters for some accumulations)

Roll back the offending change immediately. Diagnose with `git diff`.

### 9.3 Validator + min_raiser checkpoints

After every change:
```bash
.venv/bin/python sandbox/validator.py bots/skantbot8/bot.py
.venv/bin/python -m pytest tests/
.venv/bin/python _check_crn.py
.venv/bin/python _check_min_raiser_skb8.py  # adapt from _check_min_raiser_714.py
```

All four must pass.

### 9.4 Commits and tags

After each step's gates pass:
```bash
git add bots/skantbot8/bot.py harness/skantbot8_dev/bot.py [test scripts]
git commit -m "skantbot8 step N: <change>"
git tag v81-step-N-<change-name>
```

Tags let you check out any intermediate state if a later step breaks
things.

### 9.5 Documentation as you go

Each step writes a brief `V81_STEP_N_NOTES.md`:
- What was the pre-diagnostic result?
- What did paper hands look like?
- Which gates passed, which failed and why?
- If a gate failed and you fixed it: what was the root cause?

These notes are the audit trail. The next person (you, in 2 weeks; or
a different agent) reads them to understand WHY decisions were made.

## 10. Failure protocols

What to do when things go wrong. Common scenarios:

### 10.1 A paper hand doesn't match prediction

Don't proceed to implementation. Re-derive the expected behavior from
the bot's current code, then either:
- Fix the prediction (you misunderstood the bot's logic)
- Fix the implementation (your code doesn't match the design)

DO NOT decide "the paper hand was probably wrong." That's how 7.14
shipped a broken fix.

### 10.2 A validation gate fails

Roll back the change. Re-run the gate to confirm rollback was clean. Then:
- Reproduce the failure with smaller test
- Trace the specific decisions where the bot diverged
- Fix root cause OR conclude the change can't pass and remove it

DO NOT "tune" parameters to make the gate pass. That's overfitting the
test, not fixing the underlying issue.

### 10.3 V81 sweep produces a candidate that fails gates

Same as V80b's trial #189 outcome:
- If best trial fails ≥2 gates: ship 7.13+#1+#2+#5 (no sweep params)
- If best trial fails 1 gate marginally (e.g., heldout regression on
  ONE opp at 2.1σ): consider whether the regression is acceptable
  given the gains elsewhere. Get a second opinion.

DO NOT lower gate thresholds to make a trial pass. Same overfitting
concern.

### 10.4 Latency budget breached in #5

If forward-look exceeds 1.8s on any real match decision:
- Try truncated horizon (turn-only, no river forward-sim)
- Try precomputed action-line tables (offline computation)
- If neither works in <0.5 day: REMOVE #5 entirely, ship 7.13 + #1 + #2

## 11. Reference: existing files the V81 agent will use

### V80b cycle outputs (read for context)

- `V80b_POSTMORTEM.md` — full V80b cycle analysis
- `harness/results/sweep_db_snapshots/skb80b_1030.db` — V80b sweep DB
- `_analyze_v80b.py` — direction-confirmation analysis (run with skb80b_1030.db)
- `_1d_sweeps.py` — definitive 1D parameter sweeps showing no interior
  optimum for the 4 candidates tested

### Diagnostic scripts (existing, reuse + extend)

- `_check_crn.py` — CRN gate
- `_check_min_raiser_714.py` — adapt to skantbot8
- `_compare_713_vs_714.py` — adapt to compare skantbot8 vs 7.13
- `_compare_79_vs_713_heldout.py` — adapt for V81 heldout pool
- `_bust_survey_param.py` — parametrized bust survey, takes bot path
- `_paper_hands_v80c_priors.py` — example paper hand structure
- `_trace_bust_036.py` — example per-decision trace

### Failed attempts (do NOT undo, just reference)

- `bots/skantbot7.14/bot.py` — failed donk-lead-guard (7.14 attempt)
- `bots/skantbot7.14b/bot.py` — failed trial #443 sweep result

### Existing pool definitions

`harness/opponents/registry.py`:
- `TRAIN_EXPANDED` (23 opps, LLM-heavy)
- `UNSEEN_VALIDATION` (7 opps, archetype-heavy)
- Add new V81 versions, don't modify the old ones

## 12. Calendar / time math

| Step | Work time | Cumulative |
|---|---|---|
| 0. Diagnostic toolkit | 0.5 day | 0.5 day |
| 0.2 Pool bias check (decision point) | 0.1 day | 0.6 day |
| 1. Pool rebalance | 0.5 day | 1.1 day |
| 2. Bet-sizing signal | 1.0 day | 2.1 day |
| 3. Per-opp narrowing | 1.0 day | 3.1 day |
| 4. Forward-look | 2.0 days | 5.1 day |
| 5. V81 sweep + verify | 1.0 day | 6.1 day |
| **Total** | **~6-7 days** | |

If the 2nd-round competition is **2+ weeks** out: do everything.
If the 2nd-round competition is **1 week** out: skip #5, ship just #1
+ #2 + sweep.
If **3 days** out: skip everything, ship 7.13 again.

## 13. Final note to the next agent

You're inheriting:
- A working tournament bot (7.13) that's verified bust-safe
- A full diagnostic toolkit + post-mortem from V80b
- A clear plan with explicit pre-diagnostic + post-validation gates
- A user who values rigor over speed and will call you out if you
  speculate without evidence

The hardest thing about V81 won't be the code. It will be resisting the
urge to skip the pre-diagnostic and "just try it." The V80b cycle's
7.14 failure happened because I (Claude) proposed a fix without
reproducing the bust pattern first. Don't repeat that.

Read each step's pre-diagnostic. Write the trace table BEFORE the
implementation. Run the paper hands BEFORE the gates. Document as you
go. If a gate fails, roll back — don't tune around it.

The user submitted 7.13 already. There's no fire. Take the time to do
it right.

Good luck.

---

Written by Claude Opus 4.7, 2026-05-29, post-V80b cycle, post-7.13
submission. Context preserved at this state for the V81/skantbot8 agent.
