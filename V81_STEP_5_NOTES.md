# V81 Step 5 — Sweep and ship decision

## Scope

Per the 1-week timeline branch (V81_PLAN_SKANTBOT8.md §12) and Step 2
rejection: the V81 sweep tunes 7.13 + #1 (skantbot8) over a focused
14-param space. #2 params are excluded (rolled back), #5 params are
excluded (deferred), 12 V80b "dead" params are excluded per advisor
amendment.

## Param space (14)

Locked-in dropped params (would have been noise dimensions for TPE):
`stack_risk_high_threshold`, `stack_risk_medium_threshold`,
`stack_risk_high_eq_normal`, `stack_risk_high_eq_maniac`,
`stack_risk_med_eq_normal`, `stack_risk_med_eq_maniac`,
`river_v2b_pot_sized`, `river_v2b_overbet`, `sizing_polarised`,
`prior_weight`, `min_hands_for_exploit`,
`fold_to_3bet_exploit_threshold`.

Active params (`_sweep_v81.py:PARAM_SPACE_V81`):
- 3 equity / pot-odds: equity_call_threshold, pot_odds_buffer_normal,
  equity_thin_value
- 3 bluff / cbet freq: bluff_freq_ip, bluff_freq_oop, cbet_freq_base
- 3 preflop calls: threebet_call_threshold_pct,
  fourbet_call_threshold_pct, fourbet_bluff_freq
- 2 sizing / commit: k_commit, river_v2b_half_pot
- 3 **#1 RELATIVE** params (NOT absolute — landmine prevention):
  skb8_bet_to_mean_multiplier (1.2-2.0),
  skb8_min_obs_for_signal (15-50),
  skb8_min_bets_obs_for_signal (3-10)

## Sweep config

- Sampler: TPESampler(seed=42)
- Trials: 150 (vs plan's aspirational 2000; dev machine compute budget)
- n_seeds: 20 per trial × 22 train + 8 heldout opps × 6max × n_tables=15
- Workers: 24
- Anchor trial 0: current skantbot8 defaults
- Objective: `0.4 × train_mean + 0.6 × min(heldout_per_opp)`
  Single-scalar maximization. The `min` over heldout opps forces TPE
  toward solutions where NO heldout opp regresses badly (V80b's trial
  #189 catastrophic-overfit pattern would score badly here).

## Ship decision rubric (post-sweep gates)

Deterministic — no human judgment:

1. Build `skantbot8.1` from sweep best-trial params (`_build_v81_best.py`).
2. Run `_post_sweep_gates.py`:
   - Gate A: validator + pytest + CRN on skantbot8.1_dev
   - Gate B: skantbot8.1 vs min_raiser HU ≥ +5000
   - Gate D: skantbot8.1 vs 7.13 on TRAIN_EXPANDED_V81, avg Δ > 0,
     no >2σ regression
   - Gate E: skantbot8.1 vs 7.13 on UNSEEN_VALIDATION_V81, avg Δ > 0
     OR no >2σ regression
   - Gate F: skantbot8.1 vs maniac_aggro / super_nit HU, no >500 drop
   - Gate C: skantbot8.1 bust survey, showdown bust class growth ≤ 5%
     vs 7.13 baseline
   - Bonus: skantbot8.1 vs **skantbot8** on heldout_v81 (is the sweep
     actually better than the manual default?)

3. If ALL hard gates pass AND bonus shows positive Δ vs skantbot8:
   → ship skantbot8.1.
   If ANY gate fails (per failure protocol §10.2):
   → ship skantbot8 (= 7.13 + #1 manual default).

No deliberation, no tuning around failing gates.

## Sweep outcome — REJECTED

150 trials completed. Best trial #71: score 1294.7 (vs anchor 1233, +61),
in-sweep train_mean=526 / held_min=1807 / held_mean=2217.

skantbot8.1 built from trial #71 params and run through the full
`_post_sweep_gates.py` suite. All 10 plan gates passed:
- Gate A (validator + pytest 25/25 + CRN): PASS
- Gate B (min_raiser HU): skantbot8.1 +7600 (vs 7.13 +7200) — PASS
- Gate D (TRAIN_EXPANDED_V81 n=40): avg Δ +3, no >2σ — PASS by rule
- Gate E (UNSEEN_VALIDATION_V81 n=40): avg Δ **-15**, no >2σ — PASS by
  rule (avg>0 OR no regression) but DIRECTION is negative
- Gate F (maniac/super_nit HU): vs maniac_aggro Δ=-500 at threshold,
  super_nit Δ=0 — PASS by rule but borderline
- Gate C (bust class growth): showdown busts unchanged, loss -0.2%

**Bonus gate (my added rule from this notes file)**: skantbot8.1 vs
skantbot8 on HELDOUT_V81 n=40 → **avg Δ -27 chips/opp**, all 8 opps
non-positive (limp_machine -56 σ=-1.17 worst). **FAILED.**

### Ship decision: skantbot8 (NOT skantbot8.1)

Per the locked rule above ("If ALL hard gates pass AND bonus shows
positive Δ vs skantbot8 → ship 8.1; otherwise → ship 8"). Bonus is
negative → ship skantbot8.

Empirical confirmation across the same baseline (7.13) on
UNSEEN_VALIDATION_V81:
- skantbot8 alone (Step 1): **+19 chips/opp**, 7/8 opps positive
- skantbot8.1 (sweep result): **-15 chips/opp**, 4/8 opps negative

The +61 score gain reported in-sweep at n_seeds=20 was sample-size noise
— exactly the V80b lesson §2.4 the V81 plan warned about ("V80b's
reported unseen_mean for trial #189 was -198 chips/opp; reality was
-1400/opp"). The n=40 verification was added precisely to catch this;
it caught it. The rule didn't have to override empirics; it agreed.

## V81 ship candidate (FINAL)

`bots/skantbot8/bot.py` at commit `03c3db6` / tag `v81-step1-bet-sizing`.
Verified properties:
- Validator clean, 25/25 unit tests pass
- CRN paired_diff_mean = 0 on 23 train opps
- min_raiser HU +7200 ± 473 (vs +7300 baseline, Δ=-100)
- TRAIN_V81 paired-diff avg Δ +2 vs 7.13
- HELDOUT_V81 paired-diff avg Δ +19 vs 7.13, 7/8 opps positive
- Showdown bust class growth +2.7% on V81 heldout (within 5% gate),
  loss DROPPED by $19,469 (-4.7%)
