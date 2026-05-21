# skantbot 7.5 — Stage E/F findings (2026-05-21)

## STOP: 7.5 fails verification — do not ship.

### Stage E (candidate selection)
Sweep `v75_full.db`: 1000 trials, 16-solution Pareto front. Evaluated 5
candidates vs 7.4, CRN-paired (`STAGE_E_RESULTS.json`):

- **Trial 741** is the only candidate that doesn't fail the heldout-regression
  bar: heldout **+366**/match (within the ~±400 noise floor), train **−594**,
  adversarial probe **−125**. No clear edge over 7.4 on aggregate.
- 56/144/196/566 are all heldout-negative.

741's params were baked into `bots/skantbot7.5/bot.py` Config defaults
(uncommitted, dev branch) for the Stage F structural check.

### Stage F — FAILED on hand 38
Engine-built hand-38 state (`test_hand_38_leak._build_hand_38_state`), decision:

| bot | hand 38 |
|---|---|
| skantbot7 (vanilla)   | call  (the original catastrophic call) |
| skantbot7.3           | fold  |
| skantbot7.4 (shipped) | fold  |
| **skantbot7.5 / 741** | **call  ← REGRESSION** |

7.5 re-introduces the catastrophic call that the entire 7.4 cycle existed to
fix. (Hand 25 / Leak 2 *is* correct — 7.5 calls it, as intended.)

### Root cause — Stage B's pot-odds fix is incomplete
Stage B applied `effective_owed = min(owed, stack)` but left the `pot`
denominator including the opponent's **uncallable excess** (~15k chips the
short-stacked bot can never win). For all-in-over-stack spots this swings
pot_odds the wrong way — on hand 38, required equity collapses from ~47% to
~7%, so the bot calls ~25%-equity spots thinly.

Confirmed at the patched sites — e.g. `bots/skantbot7.5/bot.py:1131`:
```python
pot = state["pot"]                                          # raw pot — includes
pot_odds = effective_owed / (pot + effective_owed) ...       # opp's uncallable excess
```
`effective_owed` is capped to stack; `pot` is not. A correct fix must also cap
`pot` to the callable amount (raw pot minus the opponent's uncallable excess).

`REMEDIATION_PLAN_v75.md`'s claim that "Stage B doesn't change hand 38" is
empirically false — Stage B is exactly what flips it. Both that wrong claim and
the corrupted test assertions trace to Gemini's earlier 7.4/7.5-cycle work;
the standing rule to independently verify its output is what caught this.

### Test suites are corrupted — could not be trusted
`tests/test_hand_38_leak.py` and `tests/test_pav_bust_regression_v75.py`:
hand-38 assertions check `== "call"` while docstrings say "must fold". The
"POST-FIX assertion" comments are copy-paste duplicates of the pre-fix code.
Running pytest as-is would have *green-lit a broken bot*. Verification was
done by reading raw decisions instead.

### Recommendation
Do **not** ship 7.5/741. Options:
1. **Ship 7.4** (rollback) — 7.5 has no aggregate edge and a hand-38
   regression. Per the v75 rollback plan, 7.4 is the fallback.
2. **Fix Stage B properly** — pot-odds must use the callable pot, not the raw
   pot. Then re-verify hand 38 folds and likely re-sweep (thresholds were
   tuned against the wrong pot-odds, again). Significant rework.

Test assertions must be corrected regardless (hand 38 → `fold`).

---

## 7.6 pot-odds audit (2026-05-21) — the diagnosis was wrong

Probe (`$CLAUDE_JOB_DIR/probe_potodds.py`) over every bust-log all-in-over-stack
hand: bot's own modeled equity vs corrected pot odds (callable pot). Key rows:

```
 hand   owed  stack    pot  callpot  po_raw  po_corr  mod_eq  req_eq | 7.4  cur7.5  corrected
 h38   16466   1334  18666     3534   0.067    0.274   0.463   0.366 | fold  call    call
 h25   16716   2444  17556     3284   0.122    0.427   0.390   0.519 | fold  call    fold
```

1. **The pot-odds formula is NOT the hand-38 bug.** The bot models its hand-38
   equity at **46.3%** — not the ~25% the leak file assumed. With *correct*
   pot odds (~27%), 46% equity is a clear call. Fixing pot-odds does not make
   hand 38 fold — the corrected-formula bot still calls it.

2. **7.4 folds hand 38 by accident — two bugs cancelling.** Its equity model
   is inflated (~46%, true ~25%: Leak 1 only *half*-fixed), AND its pot-odds is
   inflated (Leak 2 unfixed → required_eq ~58%). 46 < 58 → fold. Fix either
   bug alone and the cancellation breaks; 7.5 fixed Leak 2 → hand 38 calls.

3. **The real unfixed bug is LEAK 1 — the range/equity model.** The v7.4
   "hand-38 fix" narrowed the aggressor range estimate from ~74% to ~46%, not
   to the ~25% the diagnosis says is correct. Still too wide.

4. **The "Leak 2 over-fold" diagnosis (hand 25) was wrong.** Under correct pot
   odds h25 is a fold: eq 0.390 < pot_odds 0.427. 7.4 folding h25 was correct.
   Stage B's cap made 7.5 *call* h25 — a −EV call, not a leak fix.

**Consequence:** a correct 7.6 must fix the EQUITY / RANGE model (Leak 1), not
pot-odds. Fixing pot-odds alone removes 7.4's accidental hand-38 fold. 7.4
remains the submission but its hand-38 fold is fragile (bug-cancellation).
