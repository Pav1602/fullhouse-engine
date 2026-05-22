# skantbot 7.7 Phase 2a — trace tables (pre-code review)

Shadow-instrumented 7.6: `aggressor_likely_range` computes the proposed
raise-freq-scaled range alongside the current narrowed range; `decide_postflop`
shadow-computes `eq` against both (separate RNGs — bot decisions and CRN
determinism verified unchanged, `Diff = 0.0` HU vs deterministic opponents).

## Trace 1 — A8s vs min_raiser, lost 2,184 (the target hand)

`eq` = current (vs narrowed range). `eq_prop` = with the fix. `rf` = min_raiser's
Bayesian raise-freq estimate at that point.

| # | street | action | eq (now) | eq_base | eq_prop | req_eq | note |
|---|--------|--------|----------|---------|---------|--------|------|
| 1 | flop   | raise  | 0.80     | —       | —       | —      | value-bets a good flop |
| 2 | flop   | call   | **0.29** | 0.67    | **0.64** | 0.26  | min_raiser raises → eq *collapses* 0.67→0.29 |
| 3 | turn   | check  | 0.35     | 0.68    | 0.65    | —      | |
| 4 | turn   | call   | 0.35     | 0.68    | 0.65    | 0.11   | |
| 5 | river  | raise  | 0.00     | 0.42    | 0.41    | —      | bluff-raises (eq<thin-value even un-collapsed) |
| 6 | river  | **fold** | **0.00** | 0.42  | **0.41** | —     | folds 1,092 it just bet |

**Verdict:** the fix restores the equity estimate (collapsed 0.29 → 0.64 at
decision 2; 0.00 → 0.41 at decision 6). Decision 6 is the key one — with
`eq_prop = 0.41` the bot calls a ~20%-pot-odds river bet as a 41% favourite
(+EV) instead of folding. Across HU vs min_raiser, **the fix flips 55% of
facing-bet folds (437 / 800) into calls.**

But decision 5 — the river bluff-raise — is **not** fixed by 2a: even the
un-collapsed equity (0.42) is below the thin-value line, so it is a genuine
bluff decision. That is the **2c** bug (bluffing a never-folder). 2a recovers
the chips at decision 6; 2c is still needed for decision 5. Consistent with
the multi-headed diagnosis.

## Trace 2 — the problem: the fix is NOT surgical

6-max probe, all postflop decisions with shadow data (N=1,038):

- the fix moves `eq` by **>0.10 in 56%** of decisions; **86% move UP**.
- `agg_raise_freq` seen at decision time: **median 0.79** (p10 0.36, p90 0.94).

The fix un-narrows almost every opponent's range, not just min_raiser's. Root
cause: the raise-freq stat is **mis-defined**. It uses
`postflop_bets_raises / (postflop_bets_raises + postflop_calls)` — which counts
opening **bets** (c-bets, leads) as "raises." So a normal c-betting opponent
scores a high "raise frequency" and gets de-narrowed too. The stat measures
*general postflop aggression*, not *indiscriminate re-raising*.

## The fix to the fix (recommended before coding)

Redefine the stat as a true **re-raise frequency**: of the times the opponent
**faced a bet** postflop, how often did they **raise** (vs call/fold). With
that definition:
- `min_raiser` still ≈ 1.0 (it re-raises every bet) → fully un-narrowed.
- a normal c-bettor has a *low* re-raise frequency → narrowed ~as today.

That makes the fix surgical — it only relaxes narrowing for opponents who
genuinely re-raise indiscriminately, which is the principled intent. It is
still a continuous Bayesian stat, not an archetype detector.

## Next step

Redefine the stat (add a `faced_bet` / `raised_when_faced` counter pair to
`BehaviouralProfile`, observed in `update_opponents_from_log`), re-run the
shadow probe, and confirm Trace 2's 86%/56% footprint shrinks to near-zero for
normal opponents while min_raiser stays fully un-narrowed. Only then code the
live fix. No `bot.py` decision-logic edit yet.
