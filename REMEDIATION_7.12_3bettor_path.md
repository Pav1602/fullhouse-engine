# Skantbot 7.12: Range-Model Accuracy Improvements + Decision Logging

## Honest framing

7.12 is **NOT a bust-195 closure**. It's a pair of range-model accuracy
improvements plus decision-logging instrumentation. The actual bust-195
closure must come from V80 parameter tuning (preflop defense tightening).

A prior Gemini session claimed the 3-bettor branch + texture change folded
the bust-195 flop call (eq 0.4449 → fold). That claim was independently
verified to be false: the bot still calls with eq 0.6183 / 61.8% on flop,
calls turn (70.0%), and calls river (78.8%). The structural changes are
mechanically working — base range becomes the (BB, BTN) THREEBET_FREQS
chart (~19 hand-classes) instead of an LJ-RFI fallback — but the narrowed
13-hand range still gives A4o on Ac-6s-7h enough equity to call.

The real leak in bust 195 is upstream: skantbot defends BB's 3-bet OOP with
A4o-class hands. That defense decision is parameter-tunable via
`threebet_call_threshold_pct`, `fourbet_call_threshold_pct`, and
`small_open_call_boost`, which are in scope for the V80 sweep.

## What 7.12 actually changes

### CHANGE 1 — 3-bettor base-range path in `aggressor_likely_range`

When postflop facing aggression from an opponent who 3-bet preflop, the
existing dispatch fell through to `RFI_FREQS[agg_pos]` (the opening range),
which over-estimated the opponent's range size by 5×–10× (e.g. ~130 hand
classes for SB RFI vs ~19 for BB-vs-BTN 3-bet range).

The new branch sits after the BB-defender (call-3bet) path and before the
old `aggressors == 1 → RFI` fallback:

```python
elif (agg_pf_action in ("raise", "all_in")
      and opener_seat is not None
      and opener_seat != agg_seat
      and (agg_pos, opener_pos) in THREEBET_FREQS):
    base_range = THREEBET_FREQS[(agg_pos, opener_pos)]
```

Verified firing in paper-hand traces (`_trace_3bettor_paper.py`):
- HU: BB 3-bets vs BTN → size 19 ✓
- 6max: CO 3-bets vs LJ → size 15 ✓
- 6max: BTN 3-bets vs CO → size 15 ✓
- 6max: BB 3-bets vs LJ → size 7 ✓
- Correctly does NOT fire when opp was the opener (opener_seat == agg_seat
  guard works) — falls to existing RFI path.

### CHANGE 2 — A-low-low texture reclassification

A-6-7-style boards (high card + two close low cards, rainbow) were
classified as `dry` purely by gap >= 6, when the connected low pair
actually provides backdoor draws and reasonable opponent semibluff range.

```python
if gap >= 6 and max_suit < 2:
    sorted_idxs = sorted(ranks)
    low_two_gap = sorted_idxs[1] - sorted_idxs[0]
    if low_two_gap <= 2:
        return "medium"
    return "dry"
```

Downstream effect: in `_narrow_range`, `texture != "dry"` selects the
tighter medium tier (drops 22-88/76s/87s/T9s), which tightens the
3-bettor's modelled barrel range.

Trace verified:
- A-6-7 → medium (was dry) ✓
- A-K-2 → still dry (no draws) ✓
- K-3-4 → medium (was dry) ✓
- A-2-7, A-5-9, A-T-7 → unchanged behaviour

### CHANGE 3 — Opt-in JSONL decision logging

Both submission (`bots/skantbot7.12/bot.py`) and dev
(`harness/skantbot7_12_dev/bot.py`) bots now have a `_log_decision()`
helper invoked at every return site in `decide_preflop_6max`,
`decide_preflop_hu`, `decide_postflop`, and `decide_river`.

**Submission bot:** silent by default. `CONFIG.log_path = None`. No file
I/O unless explicitly set. Validator clean (no `import os`).

**Dev bot:** reads `SKANT_LOG_PATH` from env at module load; if set,
writes one JSON-line per decision capturing: `hand_id`, `street`, `pot`,
`owed`, `stack`, `eq`, `v_range_size`, `v_range_sample`, `pot_odds`,
`required_eq`, `branch`, `action`, `match_delta`, `opp_id`, `opp_n_hands`,
`opp_rwf`.

Usage:
```bash
SKANT_LOG_PATH=/tmp/skant.jsonl .venv/bin/python sandbox/match.py \
    harness/skantbot7_12_dev/bot.py bots/skantbot7.9/bot.py --hands 100
```

CRN preserved with logging ON (verified: paired_diff_mean = 0.0 for all
23 opps in self-compare, 10,962 log lines written).

## Verification — all passing

| Test | Result |
|------|--------|
| Validator (submission) | ✅ PASSED |
| Unit tests | 25 passed |
| CRN self-compare (23 opps, dev) | paired_diff = 0.0 all opps |
| CRN with SKANT_LOG_PATH set | paired_diff = 0.0 all opps |
| Paper hands (A KK22 fold, B nut flush raise, C top set fold, F AA raise, G KJs TPGK call) | All pass |
| 3-bettor branch paper hands (A-E) | All 5 pass |
| Texture trace table (7 boards) | All match intended classification |
| Bust 014 fold preserved (target of original 7.11) | Still folds at all rwf levels |
| Paired-diff CRN: clean 7.11 vs 7.12 on train pool (30 seeds × 10 tables × 400 hands) | Clean wins +364 ± 298, σ=1.22 — chip-neutral within noise |
| min_raiser HU preservation | Preserved (rerun via comparison) |

## What 7.12 does NOT do

- Does **not** close bust_195 (verified — flop still calls)
- Does **not** reduce aggregate bust dollars (per prior bust survey;
  structural changes are pool-neutral)
- Does **not** introduce new tunable knobs

## V80 sweep — directional priors

Documented as a comment block at the top of `harness/sweep.py`. The 7.12
ship candidate provides the cleanest baseline yet to sweep against:

1. **Preflop defense should tighten** (closes bust_195 and family —
   60%+ of bust $ traces to wide 3-bet defense):
   - `threebet_call_threshold_pct`: sweep 0.10–0.20 (currently ~0.22)
   - `fourbet_call_threshold_pct`: sweep 0.08–0.13 (currently ~0.135)
   - `small_open_call_boost`: sweep 1.0–1.5 (currently ~1.7)

2. **Postflop calling tighter on wet boards**:
   - `equity_call_threshold`: sweep 0.42–0.55
   - `pot_odds_buffer_normal`: sweep 0.10–0.18

3. **Mode A cbet/bluff reduction** (known issue since 7.4):
   - `cbet_freq_base`: sweep down 0.40–0.55
   - `bluff_freq_ip`: sweep down 0.02–0.05
   - `bluff_freq_oop`: sweep down 0.01–0.03

4. **New Phase 2a knobs from 7.11** (default-only validated, all carry
   into 7.12 unchanged):
   - `committed_pot_ratio`: sweep 0.4–1.0
   - `phase2a_baseline`: sweep 0.10–0.25
   - `phase2a_denominator`: sweep 0.50–1.20

## Files

```
bots/skantbot7.12/bot.py             # new — submission (logging OFF default)
harness/skantbot7_12_dev/bot.py      # new — dev (SKANT_LOG_PATH env-driven)
harness/opponents/registry.py        # repoint SKANTBOT_TUNABLE_PATH → 7_12_dev
harness/sweep.py                     # V80 priors comment block
bots/skantbot7.11/bot.py             # restored to 6d28b2c (clean rollback)
harness/skantbot7_11_dev/bot.py      # restored to 6d28b2c (clean rollback)
```

## Methodology compliance

Per project memory (`feedback_verify_agent_changes`,
`feedback_trace_table_before_changes`):
- Advisor consulted at session start
- Paper hands written and run for every change
- Trace tables built showing intended internal-variable effect
- All Gemini-claimed verifications independently re-run; one falsification
  (bust 195 flop fold claim) caught and surfaced honestly above
- CRN preservation verified at every step
