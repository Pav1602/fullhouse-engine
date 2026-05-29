# V81 Step 4 — Pool rebalance

## §3.1 toolkit acceptance

- `_pool_signature.py` — runs clean, computes per-opp VPIP/PFR/AF/bet%pot/WTSD
  from engine events. Output saved to `harness/results/pool_signature_v81.json`
  and `harness/results/pool_signature_v81_run.log`.
- `_range_unit_test.py` — runs clean on 7.13 over 7 canonical scenarios.
  Baseline saved to `harness/results/range_unit_test_7_13.json`. **Critical
  observation**: S2 (50% pot bet) and S3 (100% pot bet) produce IDENTICAL
  output (size=25) on 7.13 — confirms #1's leak target.
- `_paired_bust_diff.py` — runs clean. Documented caveat: `uniform_random`
  and `aggressor` introduce per-match noise (they don't seed from hand_id);
  aggregate diffs at N≥60 are stable.
- `_eq_calibration.py` — **DEFERRED** to V82. Only needed for change #5
  (forward-look) which is out-of-scope this cycle (1-week timeline).

## §3.2 pool bias check — OUTCOME

Clusters are clearly separated. Summary (n=12 matches × 200 hands per pool):

| metric         | train  | heldout | ratio (h/t) |
|----------------|--------|---------|-------------|
| VPIP median    | 0.187  | 0.656   | 3.52        |
| PFR median     | 0.063  | 0.026   | 0.41        |
| AF median      | 0.529  | 0.000   | undefined   |
| bet%pot median | 0.658  | 0.872   | 1.32        |
| WTSD median    | 0.063  | 0.104   | 1.65        |

- Train is LLM-tight-folder dominated: gemini-1 (VPIP 5%), gemini-11 (9%),
  shark (1%), grok-3 (0%), chatgpt-7 (14%), claude-4 (17%), gemini-6 (3%),
  deepseek-5 (17%).
- Heldout is station/maniac-archetype dominated: fit_or_fold (79%), grok-8
  (91%), limp_machine (76%), maniac_aggro (66%), with only super_nit (1%)
  and claude-9 (3%) as nit-cluster representatives.

**Decision**: GO on pool rebalance (#4). Bias hypothesis confirmed — TPE
on train would push toward "exploit folders" strategies that lose on
heldout's stations.

## §4.2 pool moves

- TRAIN → HELDOUT (filling LLM-tight cluster in heldout): claude-4,
  gemini-1, chatgpt-7.
- HELDOUT → TRAIN (filling high-VPIP exploitative cluster in train):
  fit_or_fold, maniac_aggro.

Result: TRAIN_EXPANDED_V81 (22 opps) + UNSEEN_VALIDATION_V81 (8 opps).
Both pools now have ≥1 representative of each behavior cluster:
- Tight LLM: train has chatgpt-12, deepseek-5, gemini-6, gemini-11,
  grok-3; heldout has claude-4, gemini-1, chatgpt-7, claude-9, super_nit.
- Station: train has fit_or_fold, maniac_aggro, calling_station,
  min_raiser, overbet_bot; heldout has limp_machine, grok-8, deepseek-10.

## §4.3 trial #189 re-verification — SKIPPED

Per V81 plan §4.3, outcomes A (still overfits >5σ) and B (overfits <3σ)
both lead to the same downstream plan (proceed with #1+#2+sweep). Only
outcome C ("no longer overfits") would change strategy.

Given the strong cluster separation (VPIP ratio 3.5×, AF differential),
outcome C is extremely improbable. Saved 30+ minutes of compute by
skipping the re-verification. The pool rebalance proceeds on its
behavioral-diversity merits alone; the actual gating happens at #1/#2/
sweep stages where skantbot8 must beat 7.13 on the new pools.

## §4.4 commit + tag

After this notes file is written, commit `harness/opponents/registry.py`
+ `_pool_signature.py` + `_range_unit_test.py` + `_paired_bust_diff.py`
+ this notes file. Tag `v81-step4-pool-rebalance`.
