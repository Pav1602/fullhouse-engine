# skantbot 7.7 Phase 2a — LIVE fix verified trace table

## The fix

`aggressor_likely_range` now scales range-narrowing by the opponent's **true
re-raise frequency** (raised_when_faced_bet / faced_bet, Bayesian with prior
0.15). Only un-narrows for excess above the 0.15 population baseline:

```
reraise_freq = (raised_when_faced + 3) / (faced_bet + 20)
excess = max(0, reraise_freq - 0.15)
w = max(0, 1 - excess / 0.85)   # fraction of narrowing to keep
result = narrowed * w + base_range * (1-w)
```

- Normal opponent (reraise_freq ≈ 0.15): `w = 1.0` → **zero change from 7.6**
- min_raiser (reraise_freq ≈ 0.37–0.69): `w ≈ 0.36–0.74` → significant un-narrowing

## Verified trace — actual runtime values from the live fix

Run: `harness/skantbot7_6_debug/bot.py` (live fix + probe) vs `min_raiser`, 200 hands.
Match result: skantbot busts min_raiser in 27 hands (delta +10,000).

Three eq columns:
- `eq_7.7` — what the bot **actually computes** with the fix (verified from probe JSONL)
- `eq_7.6` — what 7.6 would compute (fully narrowed, `eq_narrowed` from probe)
- `eq_base` — equity vs the un-narrowed base range (ceiling)

### Early match (hands 3-5, faced_bet=0, w=1.0) — FIX IS INVISIBLE

| hand | st | cards | act | eq_7.7 | eq_7.6 | eq_base | w | rr | pot_odds | req_eq | Δ |
|------|-----|-------|------|--------|--------|---------|------|------|----------|--------|------|
| 0003 | flop | 75o | call | 0.413 | 0.413 | 0.547 | 1.00 | 0.15 | 0.167 | 0.241 | 0.00 |
| 0003 | turn | 75o | call | 0.355 | 0.355 | 0.581 | 1.00 | 0.15 | 0.125 | 0.199 | 0.00 |
| 0003 | river| 75o | fold | 0.000 | 0.000 | 0.518 | 1.00 | 0.15 | — | — | 0.00 |
| 0005 | flop | 74o | call | 0.812 | 0.812 | 0.807 | 1.00 | 0.15 | 0.196 | 0.270 | 0.00 |

**Zero difference.** Prior dominates when no observations exist. The fix
cannot cause any cold-start change — it degrades gracefully to 7.6 behaviour.

### Hand 0007 (A7s, faced_bet=3, w=0.921) — MILD UPLIFT

| hand | st | cards | act | eq_7.7 | eq_7.6 | eq_base | w | rr | pot_odds | req_eq | Δ |
|------|-----|-------|------|--------|--------|---------|------|------|----------|--------|------|
| 0007 | flop | A7s | call | 0.397 | 0.368 | 0.477 | 0.921 | 0.217 | 0.196 | 0.257 | +0.03 |
| 0007 | turn | A7s | call | 0.380 | 0.325 | 0.488 | 0.921 | 0.217 | 0.049 | 0.110 | +0.06 |
| 0007 | river| A7s | call | 0.344 | 0.000 | 0.485 | 0.921 | 0.217 | — | — | +0.34 |

River: 7.6 sees eq=0.00 (range collapsed to a range A7 can't beat) and would
fold. 7.7 sees eq=0.34 → calls. Against min_raiser's random range, A7 high
actually wins ~34% — the 7.7 number is correct.

### Hand 0021 (A3s, faced_bet=11, w=0.759) — LARGE EQUITY RECOVERY

| hand | st | cards | act | eq_7.7 | eq_7.6 | eq_base | w | rr | pot_odds | req_eq | Δ |
|------|-----|-------|------|--------|--------|---------|------|------|----------|--------|------|
| 0021 | flop | A3s | call | 0.682 | 0.625 | 0.728 | 0.759 | 0.355 | 0.198 | 0.259 | +0.06 |
| 0021 | turn | A3s | raise | 0.641 | 0.346 | 0.676 | 0.759 | 0.355 | — | — | +0.30 |

Turn: 7.6 equity collapsed to 0.35 → would check/fold a hand with 64% true
equity. 7.7 correctly sees 0.64 and value-raises. The +0.30 delta IS the bug
being fixed.

### Hand 0011 (J8o, w=0.828) — CORRECT FOLD PRESERVED

| hand | st | cards | act | eq_7.7 | eq_7.6 | eq_base | w | rr | pot_odds | req_eq | Δ |
|------|-----|-------|------|--------|--------|---------|------|------|----------|--------|------|
| 0011 | flop | J8o | call | 0.242 | 0.175 | 0.323 | 0.828 | 0.296 | 0.167 | 0.227 | +0.07 |
| 0011 | turn | J8o | fold | 0.165 | 0.105 | 0.195 | 0.828 | 0.296 | 0.154 | 0.215 | +0.06 |

Fix gives J8o a higher equity (+0.06) but it's still below req_eq (0.165 < 0.215)
→ **correctly folds**. The fix doesn't turn bad hands into calls — it only
restores accurate estimation. The required_eq threshold still protects.

### Hand 0023 (QJo, faced_bet=13, w=0.749) — VALUE RAISE INSTEAD OF PASSIVE CALL

| hand | st | cards | act | eq_7.7 | eq_7.6 | eq_base | w | rr | pot_odds | req_eq | Δ |
|------|-----|-------|------|--------|--------|---------|------|------|----------|--------|------|
| 0023 | flop | QJo | call | 0.717 | 0.577 | 0.757 | 0.749 | 0.364 | 0.198 | 0.259 | +0.14 |
| 0023 | turn | QJo | raise | 0.731 | 0.640 | 0.780 | 0.749 | 0.364 | — | — | +0.09 |

7.6 sees 0.58 on the flop (borderline value) and plays passively. 7.7 sees
0.72 (correct — QJ crushes min_raiser's random range) and plays aggressively.

## Summary of the trace evidence

1. **Cold start (faced_bet=0):** fix is invisible (w=1.0, eq_7.7 = eq_7.6).
2. **Learning phase (faced_bet=3–8, rr=0.21–0.32):** small uplift (+0.03–0.10).
   Marginal hands that should fold still fold (J8o, 64o, 63s all below req_eq).
3. **Converged (faced_bet=11+, rr=0.35+):** large equity recovery (+0.12–0.30).
   Bot correctly identifies value hands (A3s, QJo, K2o) and raises instead of
   folding. This is where 7.6 was haemorrhaging chips.
4. **The fix never turns a losing hand into a call** — it only corrects the
   equity estimate. The pot_odds + buffer threshold still gates the decision.

## Regression check: normal opponents

Against normal opponents (reraise_freq ≤ 0.15), `excess = 0`, `w = 1.0` →
the fix returns `narrowed` unchanged. **Zero code path difference from 7.6.**
Verified: 12 deterministic opponents show Diff = 0.0 exactly in CRN compare.

## Final numbers

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| HU vs min_raiser | ≥ +1,400 | **+7,033** (n=100) | PASS |
| No matchup >2 SE drop | — | None (det. opps 0.0) | PASS |
| No flip pos→neg | — | None | PASS |
| 6-max paired-diff vs 7.6 | ≥ 0 | Net positive | PASS |
| Validator | Clean | Clean | PASS |
| CRN determinism | Diff = 0.0 | Diff = 0.0 | PASS |

## Files changed (3 sites in bot.py)

1. `BehaviouralProfile.__init__`: +2 counters (`faced_bet_postflop`,
   `raised_when_faced_postflop`)
2. `update_opponents_from_log` (postflop block): observe `faced_bet` and
   `raised_when_faced` when `last_bettor is not None`
3. `aggressor_likely_range` (after `_narrow_range`): compute `reraise_freq`,
   blend `narrowed` with `base_range` proportional to excess over baseline

Submission bot: `bots/skantbot7.7/bot.py`
Debug bot: `harness/skantbot7_6_debug/bot.py` (with probe instrumentation)
