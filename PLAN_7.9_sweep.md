# Skantbot 7.9 — Post-Parser-Fix Optuna Sweep Plan

**Date:** 2026-05-23
**Status:** Plan agreed; sweep code + AWS launch scripts drafted; waiting on EC2 vCPU quota raise (case opened with AWS Support).
**Predecessor:** 7.8 shipped (`v7.8-stable`, commit `4ebbebe`) — parser-fix-only.

---

## Goal

Re-tune all parameters that compensated for the broken BB-defending charts in 7.4/7/7.7. The 7.8 ship already wins +1208/opp 6-max train and +1040/opp heldout vs 7.7, but regresses in HU vs polished bots (gemini-1, claude-4, gemini-6) because Optuna had tuned thresholds around the empty charts. A fresh sweep on the now-correct chart-space should recover HU and likely add 6-max gains on top.

---

## Param space — 42 params (from 92 Config fields)

### Selection methodology

Three buckets:

**Included (34 from previous shortlist):** parameters that directly compensated for the broken charts (preflop tightness multipliers, BB calling thresholds, small-open eq-rescue), plus the standard postflop equity/c-bet/bluff/opp-exploit knobs that may shift with the new preflop ranges.

**Added for sibling coherence (8):** sweeping `k_texture_paired` without `k_texture_monotone/connected/high_card` would let Optuna over-fit one texture coefficient relative to its siblings. Same for `k_bluff_vs_cbet_folder` without the `2barrel/3barrel/wtsd` siblings, and `k_standing` without `standing_alpha/beta`. All-or-none for each coherent group.

**Explicitly skipped (50):**
- 6× `pos_aggression_*` (defaults all 1.0, low signal — 6 dims for a multiplicative knob that the pool doesn't reward)
- Compute knobs (mc_sims_*, time_budget_sec) — not tactical
- Opp-classifier thresholds (prior_weight, maniac/station VPIP/PFR thresholds, min_hands_for_exploit) — calibrated, sweeping risks classifier drift
- _maniac variants of stack_risk (only fire vs detected maniacs, narrow signal)
- spr_commit_threshold/smoothness/k_commit — complex interactions, defer to a focused later sweep
- Sub-bin sizing (river_v2b_*, river_value_*_size, sizing_value/polarised/thin, preflop sizing_* multipliers) — categorical, narrow ranges, low payoff per dimension
- cold_start_caution, fold_to_3bet_exploit_threshold — narrow windows of effect

Trial density: 5000 trials / 42 params = 119 trials per dim. Adequate for NSGA-II with these ranges.

### Full v79 param list (in `harness/sweep.py:PARAM_SPACE_V79`)

```python
# A. Preflop tightness (8) — directly disrupted by parser fix
"rfi_tightness":               (1.0, 1.6),
"threebet_tightness":          (0.7, 1.3),
"fourbet_tightness":           (0.9, 1.5),
"threebet_call_threshold_pct": (0.10, 0.30),
"fourbet_call_threshold_pct":  (0.10, 0.25),
"small_open_threshold_bb":     (1.5, 3.0),
"small_open_call_boost":       (1.5, 3.0),
"small_open_3bet_boost":       (1.2, 2.5),

# B. Stack curve (2)
"shrink_widening_factor":  (0.0, 0.15),
"stack_short_tightness":   (0.6, 1.0),

# C. Postflop equity thresholds (6)
"equity_value_bet":         (0.55, 0.75),
"equity_thin_value":        (0.45, 0.62),
"equity_call_threshold":    (0.35, 0.55),
"equity_raise_threshold":   (0.75, 0.90),
"pot_odds_buffer_normal":   (0.05, 0.20),
"pot_odds_buffer_marginal": (0.10, 0.30),

# D. Stack-risk / variance (3)
"variance_c":                (0.005, 0.10),
"stack_risk_high_eq_normal": (0.65, 0.85),
"stack_risk_med_eq_normal":  (0.40, 0.60),

# E. C-bet / bluff (6) + texture-coef siblings (3) = 9
"cbet_freq_base":         (0.40, 0.80),
"cbet_size_pct":          (0.40, 0.70),
"cbet_multiway_penalty":  (0.40, 0.80),
"bluff_freq_ip":          (0.005, 0.10),
"bluff_freq_oop":         (0.01, 0.15),
"k_texture_paired":       (0.05, 0.40),
"k_texture_monotone":     (0.05, 0.30),
"k_texture_connected":    (-0.30, 0.10),
"k_texture_high_card":    (-0.20, 0.10),

# F. Opp-exploit knobs (5) + barrel/wtsd siblings (3) = 8
"k_bluff_vs_cbet_folder":         (0.0, 0.7),
"k_bluff_vs_2barrel_folder":      (0.0, 0.5),
"k_bluff_vs_3barrel_folder":      (0.0, 0.5),
"k_bluff_vs_wtsd":                (0.0, 0.30),
"k_value_size_vs_station":        (0.0, 0.40),
"k_tightness_vs_3bet_freq":       (0.0, 0.30),
"k_4bet_vs_3bet_freq":            (0.0, 0.50),
"k_call_threshold_vs_aggression": (0.0, 0.50),

# G. River + match-state (4) + standing_alpha/beta siblings (2) = 6
"river_mdf_aggression":         (0.80, 1.20),
"river_value_thin_threshold":   (0.50, 0.65),
"river_value_strong_threshold": (0.72, 0.85),
"k_standing":                   (0.10, 0.50),
"standing_alpha":               (0.02, 0.20),
"standing_beta":                (0.05, 0.40),
```

---

## Objective shape (4-axis Pareto)

```python
return (train_mean_6max, train_worst_6max, unseen_mean_6max, hu_polished_mean)
```

- `train_mean_6max`: average chip delta vs all 23 train pool opponents (6-max)
- `train_worst_6max`: per-opponent worst (robustness signal — don't let any one opponent collapse)
- `unseen_mean_6max`: average chip delta vs 7 heldout opponents (generalization signal)
- `hu_polished_mean`: NEW. Average HU chip delta vs `{gemini-1, claude-4, gemini-6}` — the three bots 7.8 regressed against in HU mode. Defaults to running at `hu_seeds=10` (cost-controlled).

Sampler: NSGA-II (Optuna's default for ≥4 objectives, better Pareto exploration than TPE in higher dim).

**Lock criteria at final selection (post-sweep, not during)**:
1. From the Pareto front, exclude any trial with `train_worst < -3000` (existing `--worst-case-floor`).
2. Among survivors, the recommended pick is the one maximizing `train_mean + unseen_mean`.
3. **Before promoting to 7.9**: verify `hu_polished_mean ≥ 7.7-baseline-mean within SE`. The advisor's hard rule — don't trade HU regression for 6-max gain.
4. If no trial passes (3), inspect the Pareto front and accept the best-HU trial that still beats 7.8 on 6-max.

---

## Compute strategy

**Hardware**: c7i.48xlarge (192 vCPU, 384 GB RAM, eu-west-2)
**Configured parallelism**: `n_jobs=12 × n_workers=16 = 192 vCPU`

**Per-trial timing (MEASURED 2026-05-23, not extrapolated):**
- Local at n_workers=6, n_jobs=4: 530-540s per trial measured (4 trials timed)
- Scaling to cloud n_workers=16 (more parallelism within trial): ~200-250s per trial expected
- With n_jobs=12 parallel trials on cloud, effective per-trial wall ≈ 200-250s

**Total trial budget options:**

| Trials | Seeds | Cloud wall (est) | Cloud cost (spot) | Cloud cost (on-demand) |
|---|---|---|---|---|
| 2000 | 40 | ~12-14 hr | $22-26 | $103-120 |
| 3000 | 40 | ~17-21 hr | $31-39 | $145-180 |
| 5000 | 40 | ~28-35 hr | $52-65 | $240-300 |
| 3000 | 30 (faster) | ~14-17 hr | $26-32 | $120-145 |

Spot pricing assumed $1.84/hr; on-demand $8.57/hr in eu-west-2.

**Recommendation**: 3000 trials at 40 seeds, **spot**. ~$35 expected, fits in $89 budget twice over (allows one retry if interrupted). Original 5000-trial plan blows past budget on on-demand; spot fits but takes 28-35hr.

Phase breakdown per trial:
- Phase 1: batch_size=10 quick eval on train pool
- Phase 2: 30 more seeds full eval on train pool
- Phase 3: 40-seed heldout eval
- Phase 4 (v79 only): hu_seeds=10 HU compare vs polished bots

**Quota status (2026-05-23)**:
- Spot vCPU (L-34B43A08) requested 192 — `CASE_OPENED` with AWS Support
- On-demand vCPU (L-1216C47A) NOT yet requested — spot is the recommended path anyway given cost

**Quota status (2026-05-23)**:
- Spot vCPU (L-34B43A08) requested 192 — `CASE_OPENED` with AWS Support
- On-demand vCPU (L-1216C47A) NOT yet requested — needs separate request if user wants on-demand

---

## Code-to-instance path

Two options:

**(A) rsync from local — current README recommendation**
- Captures any uncommitted local changes
- No git auth needed on instance
- Documented in `aws-launch/README.md`

**(B) git clone from origin**
- Cleaner if running multiple sweeps
- Requires: push commits/tags to origin first; either public repo OR PAT/SSH on instance
- For a one-off, the auth setup isn't worth it

Recommend (A) for this sweep.

---

## Files in this plan

- `harness/sweep.py` — modified: `PARAM_SPACE_V79`, `HU_POLISHED_OPPONENTS`, new CLI flags `--param-set`, `--hu-seeds`, `--n-jobs`, NSGA-II sampler for ≥4 objectives, 4th-objective HU compare in `make_objective`
- `aws-launch/user-data.sh` — boots Ubuntu 24.04 + installs python3.12 + eval7 + optuna
- `aws-launch/run-sweep.sh` — wraps the python -m harness.sweep call with env-var-driven knobs
- `aws-launch/launch.sh` — `aws ec2 run-instances` for c7i.48xlarge with prereq notes
- `aws-launch/README.md` — full step-by-step including termination instructions

---

## Risks

| Risk | Mitigation |
|---|---|
| Quota request denied / takes >48hr | Fall back to local 28-thread (~30hr) |
| Spot instance interrupted mid-sweep | Optuna DB persists on EBS, can resume on new instance with `--resume`. ~30min recovery. |
| Sweep finds best on 6-max but tanks HU | Lock criterion #3 catches it; don't ship. Investigate why and re-sweep with HU weight bumped. |
| Forgotten instance running for days | README has explicit termination command. Set a phone reminder. |
| Sweep params drift sweep results out of training distribution | Each trial evaluates on heldout, so generalization is measured. |
| EBS volume not deleted with instance | `DeleteOnTermination=true` is set on `/dev/sda1` in `launch.sh`. |
