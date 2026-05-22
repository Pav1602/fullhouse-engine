# skantbot 7.7 — Stage 1 Diagnosis (instrumented, pool-measured)

**Method:** instrumented copy of 7.6 (`harness/skantbot7_6_debug/bot.py`),
verified bit-identical to 7.6 (`Diff = 0.0 ± 0.0` HU vs deterministic
opponents, both before and after the P&L extension). Probes:
- 6-max: 7.6 vs 23-bot training pool, 15 seeds × 10 tables × 200 hands
- HU: 7.6 vs each pool opponent, 20 seeds × 200 hands
Per-decision JSONL + per-hand P&L records. Analysis: `harness/probe_7_6_analyze.py`.

## Bottom line — the plan's premise does not survive measurement

The 7.7 plan assumes a **broad passive-over-calling bleed**. The pool data
says otherwise:

- **P&L of `eq_override` calls is POSITIVE**, not negative:
  6-max **+156.6/hand** (vs +55.3 all-hands avg); HU **+70.8/hand** (vs +50.6).
  Calling min-raises wide is *net +EV against this pool*.
- **HU, 7.6 beats 22 of 23 pool opponents.** It loses to exactly one:
  `min_raiser` at **−1,759/match** (the sole negative matchup; next-worst
  is `aggressor` at only +1,250). 6-max vs `min_raiser`: **+10,241** (a
  table full of other bots punishes the min-raiser; skantbot's own calls
  are not what drives that).

So there is **no general bleed**. There is **one isolated, real
vulnerability**: against a preflop **min-raiser**, the small-open
equity-override over-calls and the bot then cannot realise its equity. The
human game exposed it because the human min-raised. The harness pool masks
it because it contains only one true min-raiser and 6-max dilutes it.

## The mechanism (confirmed, HU and 6-max identical)

Facing a single open, action by open size:

| open type            | fold  | call  | 3bet  | (6-max N / HU N) |
|----------------------|-------|-------|-------|------------------|
| min-raise (≤2.067bb) | ~1.5% | ~90%  | ~8.5% | 1,397 / 1,743    |
| normal/large open    | ~88%  | ~2%   | ~9%   | 1,729 / 3,427    |

- Against a normal open the bot is correctly tight (~88% fold). Against a
  **min-raise it folds ~1.5% and calls ~90%.**
- ~95% of those calls come from the **small-open equity-override branch**
  (`decide_preflop_6max` bot.py:1250-1254; `decide_preflop_hu` ~1487-1491):
  when the chart call-freq is 0, it calls anyway if
  `eq_heuristic ≥ pot_odds / small_open_call_boost` (`small_open_call_boost
  = 2.30` → near-zero equity bar). The chart branch (`call_table`) fires
  <5% of the time.
- Hand mix of those min-raise calls: ~80% non-pair / non-broadway, mostly
  offsuit gappers (K6o, 97o, 53o-type) — the human-log hands exactly.
- This fires whenever **any** opponent min-raises, at **any** hand count —
  flat across `hands_observed` buckets. **Not a cold-start phenomenon.**
  (→ the Stage-S "early-game-weighted objective" open question is moot.)

## Two further observations — real, but the pool cannot price them

These are mode-independent (HU ≈ 6-max) and genuine, but the pool P&L is
already +EV, so the harness **cannot measure them as leaks**:

- **Mode A still live:** flop c-bet **80%** (HU 79%), turn ~57%, river ~53%.
  An 80% flop c-bet is wide. Carries 7.4's params, never fixed.
- **No caller aggression:** as the caller facing a bet the bot raises
  **1.9%** (HU 2.0%) — and only with ~92% equity. Calls down at coinflip
  equity, folds the rest. No floats, semi-bluff raises, or check-raises.

## Why this reframes 7.7

The plan's "one root, two symptoms, structural bleed" framing is a story
the data does not support. What the data supports:

1. **One isolated vulnerability** — min-raise over-call — that is real,
   measurable (`min_raiser` HU −1,759), and the *only* losing matchup.
2. **Two style observations** (Mode A, caller-passivity) that are NOT
   bleeds against any opponent the harness can run. Chasing them with a
   sweep or structural change risks regressing the 22 +EV matchups to fix
   a leak the pool cannot see — exactly the v75 mistake.

## UPDATE — the equity-override is exonerated; the leak is a bust pattern

Per-opponent P&L of `eq_override` hands (HU probe): the branch is **+EV vs
`min_raiser`** (+120/hand, the opponent it fires against most). It only
shows a loss vs `chatgpt-7` (-258/hand, 131 calls). The plan's prime
suspect — the small-open equity-override — is **not** the cause of the
`min_raiser` loss.

The real `min_raiser` mechanism, from match-level P&L: of 40 HU matches,
**24 end -10000 (skantbot busts), 14 end +10000, 2 partial** — almost pure
all-or-nothing, ~70 hands/match. It is a **bust-rate** problem, not a slow
bleed.

`min_raiser` (`archetypes/min_raiser/bot.py`) min-raises **every street,
every decision**, escalating to all-in. Each individual min-raise is cheap,
so skantbot's per-decision pot-odds call logic accepts every one and is
"frog-boiled" into stacking off a marginal hand. skantbot has no notion
that the *cumulative* line has gone bad — it re-evaluates each tiny raise
on local pot odds. That is the structural vulnerability, and it is what a
human min-raising the bot would exploit.

## Honest assessment of 7.7

1. **No broad bleed exists.** 7.6 is +EV vs 22/23 HU opponents and the whole
   6-max pool. The plan's "long-standing passive bleed" premise is refuted.
2. **The one negative matchup** (`min_raiser`, −1,759 ± 1,055 at n=40 —
   barely significant; **n=200 re-baseline pending**) is a bust-rate /
   frog-boiling pattern, not the passive over-calling the plan described,
   and **not** the eq_override branch.
3. **Mode A and caller-passivity** are real but unmeasurable as leaks — the
   pool prices them as +EV. Chasing them is the v75 mistake.
4. The frog-boiling fix is a **structural change to the postflop call
   logic** — exactly the big, risky piece the plan flags for possible 7.8
   deferral, and it targets a single pure-archetype opponent.

**Limitation (named explicitly):** the min-raise bust pattern is the only
leak the *harness can see*. The human game may have exposed other things
the human read as "passivity"; the harness pool cannot verify a fix for
them, so 7.7 deliberately does not chase them. This is a known blind spot,
not a claim that 7.6 is leak-free.

## n=200 re-baseline — the leak is confirmed real

HU baseline, 7.6 vs pool, **n=200 seeds**:

| matchup     | A_mean   | ± SE  |
|-------------|----------|-------|
| min_raiser  | **−2,493** | 461 |
| aggressor   | +777     | 465   |
| all_in_monkey | +1,950 | 469   |
| (all 20 others) | +2,000 … +10,000 | |

`min_raiser` is the **sole negative matchup**, now > 5 SE from zero — the
loss is statistically solid (not the marginal n=40 signal). True cost
≈ −2,500 chips/match HU.

## Stage-2 scope and locked success criteria

**Scope:** narrowly the **frog-boiling bust pattern** — skantbot has no
cumulative-commitment sense in the postflop call path; it accepts each
cheap min-raise on local pot odds and stacks off. The fix is a
cumulative-commitment guard (track total chips committed this hand /
this line; tighten the call requirement as cumulative commitment rises).
NOT a sweep — this is a structural gate, not a parameter to tune.

**NOT in scope:** the eq_override branch (exonerated, +EV), Mode A,
caller-passivity (unmeasurable as leaks).

**Locked success criteria — write once, do not move:**
1. HU vs `min_raiser`: improvement ≥ +1,400 (≈ 3 SE; −2,493 → ≥ −1,100).
2. HU regression guard: **none** of the other 22 matchups drops > 1 SE;
   **none** flips positive→negative; the 22-matchup aggregate does not
   drop > 1 SE.
3. 6-max: paired-diff vs 7.6 ≥ 0 (no 6-max regression — that is where the
   7.6 heldout gain lives).
4. Validator clean; cross-process determinism (`Diff = 0.0` HU vs
   deterministic opponents); bust-suite no regression.
5. **If any criterion fails → ship 7.6.** 7.6 is already +EV vs 22/23 HU
   and the whole 6-max pool; 7.7 is upside only.

**Open risk:** the fix touches the postflop call path — the plan's largest,
riskiest piece, flagged for possible 7.8 deferral. It also targets a single
pure-archetype opponent; a real-tournament min-raiser is rare. The
cost/benefit (≈ +2,500 chips vs one HU opponent, vs structural-regression
risk across 22) is a genuine ship/no-ship judgement — advisor + user gate
before any code change.

## Artifacts

- `harness/skantbot7_6_debug/bot.py` — instrumented 7.6 (probe gated on
  `SKANT_PROBE_DIR`; bit-identical to 7.6 when unset).
- `harness/probe_7_6_analyze.py` — analysis.
- `harness/results/probe_7_6/`, `probe_7_6_hu/` — raw JSONL (not committed).
