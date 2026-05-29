# V80b Sweep + 7.14 Fix Attempt — Post-mortem

## TL;DR

V80b sweep ran 1110 trials before spot interrupt. Best trial #189 overfit train pool (heldout σ=+9.29 to 7.13). Attempted surgical donk-lead-guard fix as 7.14 — also failed (heldout σ=+5.77 vs 7.9). 1D parameter sweeps and action-distribution analysis confirmed **Pareto saturation** — 7.13's structural fixes trade bust dollars for routine chip yield, and no parametric or simple structural fix can break the coupling.

**Final decision: ship 7.13 (commit `aad7256`).**

## What was tested

### V80b sweep
- 60 params over 5000 trial target, 1110 trials completed (spot interrupted)
- Anchored 7.13 defaults as trial 0
- Best trial #189: train_mean=+1448 (vs anchor +1130, +317 improvement)
- Verification on heldout: trial #189 lost +10,038 chips to 7.13 (σ=+9.29)
- Trial #443 (best by unseen objective): less bad, still lost (σ=+4.93)
- TPE's own unseen estimate was -198 chips; reality was -1400/opp

### Surgical fix attempt (7.14)
- Architecture A: in `can_check` branch, if opp raised back ≥2 times postflop AND eq < 0.85, force check
- Hypothesis: blocking the donk-lead-into-tight-raiser cascade saves chips
- **Failed:** 7.14 vs 7.13 heldout +931, 7.14 vs 7.9 heldout +8593 (worse than 7.13's +6935)
- Root cause: the guard intercepted legitimate value-bet spots more often than it intercepted bluff cascades

### Diagnostic phase (per user-requested rigor)
1. **Per-decision trace of bust_036_h0122**: 7.13 with same hand_id seed actually CHECKS the turn/river in 9/10 hole-card variants. The actual bust was a ~4% probabilistic bluff-barrel roll (line 2115).
2. **5 single-param point tests vs 7.13 on heldout**: only `pot_odds_buffer_normal=0.15` showed +1120 chips. At n=40 seeds (proper power), signal collapsed to +104 (σ=+0.04) — noise.
3. **1D sweeps on 4 candidates × 5 values each** (~7 min total):
   - `pot_odds_buffer_normal`: signal/noise = 0.89 (flat)
   - `equity_call_threshold`: signal/noise = 0.61 (flat). Best value IS the current default (0.39).
   - `bluff_freq_oop`: edge effect at 0.07 (not interior)
   - `cbet_freq_base`: edge effect at 0.50 (not interior)
4. **Action distribution analysis on river_fold_after_invest busts**:
   - 7.9 heldout: 3 busts, $10k
   - 7.13 heldout: 31 busts, $128k (10x more)
   - Same decision shape (skant donker 55-100%, ~3 opp raises/hand) just 10x frequency

## What we learned

### V80b directional priors — 9/10 confirmed
TPE found train-improving values for 9 of 10 hypothesized directions:
- `equity_call_threshold` ↑ ✓ (within bounds; current is local max)
- `pot_odds_buffer_normal` ↑ ✓
- `cbet_freq_base` ↓ ✓
- `bluff_freq_ip/oop` ↓ ✓
- `threebet_call_threshold_pct` ↓ ✓
- `fourbet_call_threshold_pct` ↓ ✓
- `small_open_call_boost` ↓ ✓
- `fourbet_bluff_freq` ↓ ✓
- `k_commit` ↓ ✗ (V80b found ↑; advisor argues this caused overfit, 1D test showed ↓ also hurts. Stays at current.)

### Train/heldout pool bias is structural
- TRAIN: 23 opps, dominated by LLM bots (claude-2/4/7/11/12, gemini-1/6/11, grok-3, chatgpt-2/7/12, deepseek-5, mathematician)
- HELDOUT: 7 opps, mostly adversarial archetypes (super_nit, fit_or_fold, maniac_aggro, limp_machine, claude-9, deepseek-10, grok-8)
- Behavioral distributions differ → TPE-tuned configs on train generalize poorly to heldout
- Even 7.13's structural fix has this asymmetry: tight range model + commitment-aware folding helps vs LLMs, costs chips vs unpredictable archetypes

### Pareto saturation confirmed empirically
The 7.13 trade-off is on a local Pareto frontier:
- $300k bust dollars saved on heldout = $300k routine chip-bleed cost
- 1D sweeps show current defaults are at local optima for the most-important params
- Action distribution shows the same decision shape across 7.9 and 7.13, just different frequencies
- The frequency increase is coupled to the tight range model — can't be surgically separated

### Sweep design issues that contributed to V80b's failure
1. **`unseen_mean` objective evaluated against UNSEEN_VALIDATION (heldout), but the train/heldout SPLIT was the issue** — heldout opps are systematically different from train, so optimizing train pushed away from heldout
2. **60-dim space with 1110 trials = ~18 trials/dim** — undersized for TPE convergence (rule of thumb 50-100 trials/dim)
3. **Multi-objective Pareto front let train_mean dominate** — no scalar enforcement of train+heldout balance

## V80c design (NOT executed)

For if/when V81 cycle proceeds:
- ~12 focused params (tighten cbet/bluff, equity thresholds, river V/B ratios)
- Single weighted objective: `0.35 × train_mean + 0.65 × min(per_opp_chip_delta on heldout)` — forces balance
- Archetype-heavy train pool (move super_nit, fit_or_fold, maniac_aggro from heldout to train; shrinks heldout to 4)
- 2000-2500 trials anchored to 7.13
- Estimated ~6-7hr / $13 spot

**NOT recommended for THIS submission cycle.** Empirical 1D sweeps show no detectable signal in the param dimensions; V80c would likely also chase noise.

## Files committed for the record

- `_analyze_v80b.py` — V80b convergence/direction analysis
- `_compare_713_vs_714.py` — full paired-diff vs 7.13 on train+heldout
- `_compare_79_vs_713_heldout.py` — 7.9 vs 7.13 heldout (the surprising finding)
- `_bust_survey_param.py` — parametrized bust survey
- `_trace_bust_036.py` — per-decision trace of one bust
- `_paper_hands_v80c_priors.py` — failed attempt to validate priors via paper hands
- `_test_v80c_priors_empirical.py` — single-point empirical tests
- `_verify_pot_odds_15.py` — n=40 verification of one signal (collapsed to noise)
- `_1d_sweeps.py` — the definitive 1D parameter sweeps (all flat)
- `_verify_714_full.py` — 7.14 verification gates (failed gates 4 + 6)

## What to do for V81

1. Address the train/heldout pool design first — make them behaviorally similar OR explicitly optimize for both
2. Consider non-parametric improvements (e.g., calibrated equity models, better opp classification)
3. If running another sweep: focused param space, single weighted objective with `min` over heldout opps, archetype-heavy train pool
4. Build the diagnostic toolkit further (action distribution analysis was useful)
