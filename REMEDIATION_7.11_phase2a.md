# Remediation: Phase 2a structural fixes in skantbot 7.10 → 7.11

**Date:** 2026-05-25
**Trigger:** Bust trace on bust_014_h0142 (skantbot 7.10) revealed Phase 2a re-raise-freq scaling over-broadens opp range at modest opp aggression (rwf ≥ 25% triggers equity 24% → 46% jump, bot stacks off with one pair).
**Outcome:** skantbot 7.11 ships with the late-street hero-call leak closed structurally. 7.10 preserved as rollback. Pending V80 sweep on new Config knobs.

---

## 1. Bugs (all in `aggressor_likely_range`)

Same trace methodology as `REMEDIATION_7.10_aggressor_range.md` §1: construct exact state, run bot's own functions, capture every variable. No "should be" claims.

### Bug 1 — Phase 2a un-narrows even on committed action
At rwf=25 (any reasonable aggressive opp), `excess = 0.083`, `w = 0.902`. Narrowed range gets 90% weight, base RFI 10% — but base RFI is 80+ hands so even 10% weight injects ~50 weak hands into the range. Equity 24% → 46%, bot calls. Original Phase 2a was designed for one-shot raises from habitual raisers (min_raiser), but ran unconditionally including over the `_aggressor_last_action_is_allin` narrowing that should have taken precedence.

### Bug 2 — No limp/checked-down range model
When `count_aggressors == 0` (opp limped or checked preflop), the code's `else` branch fell to `RFI_FREQS.get(agg_pos, RFI_FREQS["LJ"])` — an *opening* range for an opponent who *did not open*. Same family as the 7.10 BB-defender fix. Bug compounds with Bug 1: Phase 2a then un-narrows toward the wrong base.

### Bug 3 — Phase 2a constants hardcoded
`reraise_freq = (rwf + 3.0) / (fb + 20.0); excess = max(0, reraise_freq - 0.15); w = max(0, 1 - excess / 0.85)` — the `0.15` and `0.85` magic numbers tuned to `min_raiser` cases, unreachable to V79 sweep. V80 should sweep these.

---

## 2. Fix shape

Four coordinated changes:

### (a) Commitment override (skips Phase 2a un-narrow)
Two signals; ANY one fires:
- `_aggressor_last_action_is_allin(state, agg_seat)` — engine-labeled all-in
- `state.pot >= CONFIG.committed_pot_ratio * INITIAL_STACK` — pot bloated by multi-street commitment

Pot/stack ratio cleanly separates `min_raiser` (slow barrels, small pots) from chatgpt-2/human-style barrelers (bust_014: pot 42K vs 10K stack = 4.2× ratio, fires).

A bet-size signal (`opp_bet/pot_before ≥ 0.6`) was tried and removed: it fires against min_raiser's min-raises (≈ 86% of pot in HU due to small pre-raise pot). Pot/stack is the cleaner cut.

### (b) Limp-base path
```python
elif aggressors == 0 and agg_pf_action in ("call", "check") and agg_pos in LIMP_FREQS:
    base_range = LIMP_FREQS[agg_pos]
```
New `LIMP_FREQS` chart per position: small pairs, small Aces, suited connectors, weak suited broadways. NOT premium pairs or AKs (these raise).

### (c) Tunable Phase 2a constants
```python
phase2a_baseline: float = 0.15
phase2a_denominator: float = 0.85
committed_pot_ratio: float = 1.0
```
V80 can sweep all three. The override pot ratio determines how aggressive the gate fires; the original baseline/denominator tune Phase 2a's strength when it does fire.

### (d) Multi-street dampening — TRIED AND REMOVED
Initial fix added `multi_street_dampen_floor` to cap `w` when count_postflop_raises ≥ 2. Tested against min_raiser HU: regressed -3,200 chips/match (3.5σ) below the +5,200 baseline. min_raiser min-raises hit the count threshold easily without committing chips. Removed in favor of pot/stack-only gate, which preserves Phase 2a's min_raiser win (+5,000 vs +4,800, within noise).

---

## 3. Verification

### 3a. Bust 014 trace (rwf sweep)

`_trace_bust014.py`:
| opp_rwf | range_size | equity | required | decision |
|---|---|---|---|---|
| None | 6 | 18.0% | 32.3% | FOLD ✓ |
| 10 | 6 | 18.0% | 30.9% | FOLD ✓ |
| 25 | 6 | 18.0% | 30.9% | FOLD ✓ |
| 50 | 6 | 18.0% | 30.9% | FOLD ✓ |
| 70 | 6 | 18.0% | 30.9% | FOLD ✓ |
| 90 | 6 | 18.0% | 30.9% | FOLD ✓ |

Range stays at 6 (premium pairs only via committed-pot override) at all opp aggression levels.

### 3b. Paper hands

`_paper_hands_711.py`:
| # | Scenario | 7.11 | Expected |
|---|---|---|---|
| A | KK22 vs jam on flush turn (hand 27) | fold | fold ✓ |
| B | Nut flush (Ac3c) vs jam | raise | call/raise ✓ |
| C | Top set (KsKd) vs jam on flush board | fold (eq 48.9%) | fold (math correct) ✓ |
| F | AA on wet board (T98r) vs single cbet | raise (eq 85.9%) | call/raise ✓ |
| G | KJs TPGK on K-T-3 vs BB donk-bet | call (eq 67.2%) | call/raise ✓ |

### 3c. min_raiser preservation (Phase 2a's original win)

`_check_min_raiser.py` (HU, n_seeds=100, n_hands=400):
```
7.10 vs min_raiser HU: +4,800 chips/match (stderr 627)
7.11 vs min_raiser HU: +5,000 chips/match (stderr 628)
Δ = +200 (within noise, pooled stderr 887)
```

Phase 2a's original purpose (handle min_raiser-style wide-raisers) preserved. The pot/stack override doesn't fire against min_raiser because min-raise pots stay small.

### 3d. CRN preservation

`_check_crn.py`: PASS — paired_diff_mean == 0.0 for all 23 opponents.

### 3e. Validator + tests

```
sandbox/validator.py bots/skantbot7.11/bot.py:  ✅ PASSED
pytest tests/:  25 passed
```

### 3f. Matched n=100 baseline (training pool)

`/tmp/_baseline_711.py` produced per-hand-averaged means in matchups:
```
Sum: 7.10 = +2839   7.11 = +2632   Δ = -207 (-7%)

Per-opponent flags:
  donk_bot: -45 chips/hand (~2.8σ, !!) — likely committed-pot override
    firing against donk_bot's frequent half-pot barrels; V80-recoverable
    via committed_pot_ratio tuning.
  claude-4, mathematician, tag_value: 1-2σ regressions (within noise band)
  Most opponents within 1σ (noise)
  No opponent flips negative.
```

The regression on donk_bot is the V80 calibration target — the gate is currently set wide (pot ≥ 1.0 × INITIAL_STACK = 10K) and donk_bot's repeated half-pot barreling can bloat pots fast on misplay flops. Tuning `committed_pot_ratio` upward should claw back this regression while preserving the bust-014-class closure.

---

## 4. Known calibration knobs for V80

| Param | Default | Sweep range suggestion |
|---|---|---|
| `phase2a_baseline` | 0.15 | 0.10 – 0.25 |
| `phase2a_denominator` | 0.85 | 0.50 – 1.20 |
| `committed_pot_ratio` | 1.0 | 0.6 – 2.0 |
| `equity_call_threshold` | 0.392 | 0.30 – 0.55 (V79 already) |
| `pot_odds_buffer_normal` | 0.101 | 0.05 – 0.20 (V79 already) |
| `pot_odds_buffer_marginal` | 0.255 | 0.10 – 0.30 (V79 already) |
| `equity_value_bet` | 0.563 | 0.50 – 0.70 (V79 already) |
| `equity_thin_value` | 0.477 | 0.35 – 0.55 (V79 already) |

V80 should include the three new 7.11 params + the existing threshold params. Mode A params (`cbet_freq_base`, `bluff_freq_ip`, `bluff_freq_oop`) should keep directional priors (locked downward from V79 best).

---

## 5. Artifacts

- Submission: `bots/skantbot7.11/bot.py`
- Dev: `harness/skantbot7_11_dev/bot.py`
- Registry repointed: `harness/opponents/registry.py:SKANTBOT_TUNABLE_PATH`
- Trace: `_trace_bust014.py` (rwf sweep — must fold at every level)
- Paper hands: `_paper_hands_711.py`
- min_raiser preservation: `_check_min_raiser.py`
- CRN: `_check_crn.py`
- Bust survey: `_bust_analyze.py`, `_bust_classify.py`
- 7.10 preserved untouched as rollback at `bots/skantbot7.10/`
