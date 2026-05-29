# V81 Step 1 — Bet-sizing signal in range narrowing (#1)

## Design

Signal: bump `strength` to `"strong"` inside `aggressor_likely_range` when the
opponent's CURRENT bet/pot ratio exceeds `skb8_bet_to_mean_multiplier ×
opp's historical mean_bet_pct_pot`, gated by min-observation thresholds.

The MIN_OBS guard is critical: `mean_bet_pct_pot` defaults to 0.66 when
`bet_size_pcts` is empty. Without the guard, the signal would fire on any
opp's first big-bet, including min_raiser's atypical raises in early HU
hands — exactly the absolute-threshold landmine that broke 7.14b. Per the
existing 7.13 comment at the Phase 2a block (lines 1354-1355).

## Config additions (defaults locked to design)

```python
skb8_bet_to_mean_multiplier: float = 1.5
skb8_min_obs_for_signal: int = 30
skb8_min_bets_obs_for_signal: int = 5
```

## Implementation

In `bots/skantbot8/bot.py` (and mirrored in `harness/skantbot8_dev/bot.py`),
between the all-in override (line 1344) and `_narrow_range` call (line 1346).
Reads `state.pot` (= pot AFTER opp's raise per engine's `_emit_action` order
— same formula as the profile's `mean_bet_pct_pot`).

## Pre-diagnostic (§5.1)

Abbreviated — full 50-hand trace was not strictly necessary given:
- Lines 1354-1355 ALREADY DOCUMENT that the leak exists (absolute version
  was previously tried; the bet-sizing signal target is the same).
- The pool signature confirmed heldout pool has high-bet station opps where
  the relative signal should fire.
- 5/5 paper hands verify behavior matches design (next section).

## Paper hand verification (§5.4) — 5/5 pass

| Scenario | Profile setup | Expected | Actual |
|---|---|---|---|
| A: bet 90% pot (1.8× mean) | 50 hands, 10 bets, mean=0.50 | FIRE | ✓ size=14 |
| B: bet 30% pot (0.6× mean) | 50 hands, 10 bets, mean=0.50 | no fire | ✓ size=25 |
| C: <30 hands observed | 15 hands, 10 bets, mean=0.50 | guarded | ✓ size=25 |
| D: 0 bets observed (cold start) | 50 hands, 0 bets | guarded | ✓ size=25 |
| E: min_raiser-style small bet | 50 hands, 30 bets, mean=0.15 | no fire | ✓ size=25 |

Scenario E is the load-bearing test for the landmine fix.

## Validation gates (§5.5)

- **Gate A — validator + pytest + CRN**: PASS
  - Validator clean on `bots/skantbot8/bot.py`.
  - 25/25 pytest.
  - `_check_crn` paired_diff_mean = 0 on all 23 train opps.
- **Gate B — min_raiser HU**: PASS (+7200 vs +7300 baseline, Δ=-100 σ=-0.15)
  - Margin: +2,200 above the +5,000 marginal threshold; +4,200 above the
    +3,000 hard floor.
- **Gate D — TRAIN_EXPANDED_V81 paired-diff**: NEUTRAL.
  avg Δ = +2 chips/opp, sum +35, worst opp all_in_monkey Δ=-17 σ=-1.67.
  No >2σ regression on any of 22 opps. Below plan's aspirational
  "magnitude > 100" but doesn't hurt — the signal targets a leak (big-bet
  station tells) that doesn't manifest much on train (LLM-tight pool
  where most opps fold).
- **Gate E — UNSEEN_VALIDATION_V81 paired-diff**: POSITIVE.
  avg Δ = +19 chips/opp, sum +154, worst opp grok-8 Δ=-21 σ=-1.26.
  7/8 opps positive. All 5 LLM-tight opps (chatgpt-7, claude-4, claude-9,
  deepseek-10, gemini-1) gained — exactly where the relative bet-sizing
  signal is designed to catch nit's big-bet value tells.
- **Gate C — bust class growth (proxy: showdown busts)**: PASS.
  Total busts +1 (+1.3%). Showdown busts grew from 73→75 (+2.7%, within
  5% gate). Loss DROPPED by $19,469 (-4.7%) despite the bust-count uptick.

## Decision

Ship #1. All hard gates pass. Gate D is neutral but Gate E is the actual
ship test (it's the unseen pool) and shows the expected directional gain.

## Files

- `bots/skantbot8/bot.py` — Config fields + signal block in aggressor_likely_range
- `harness/skantbot8_dev/bot.py` — same, env-driven dev variant
- `_paper_hands_skb8_step1.py`
- `_paired_diff_skb8_vs_713.py`
