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

## The leak is real but narrow — and may not transfer

`min_raiser` is a **pure archetype**: it min-raises *every street, every
decision*, escalating to all-in. The bust pattern (60/40 against skantbot)
is a Bernoulli-on-busts process: ~95% of matches end in a bust either way.
A real Day-5 opponent who min-*opens* but plays normally postflop will not
trigger the escalation. So the −2,493 cost is **largely specific to this
degenerate archetype** and likely does not transfer to the tournament.

Note on fix mechanism: `min_raiser` does **not** fold to a 3-bet — its code
re-min-raises any raise and only checks/calls/folds once it is already
near-all-in (`chips_to_raise >= stack`). So a "3-bet it off the pot" fix
will not work as stated; 3-betting wider just escalates the pot. Any fix
path's efficacy must be **measured**, not assumed.

## Trace-table breakdown of the leak (real probed hands)

Every `min_raiser` HU big-loss hand (≥1,500 chips, n≈63) was traced
decision-by-decision with the bot's actual internal values (`eq`,
`pot_odds`, `required_eq`, `commitment_factor`, cumulative committed).
The leak is **multi-headed**:

| component | ~count | mechanism | fix |
|-----------|--------|-----------|-----|
| Postflop light-call invest-then-fold | ~14 | calls each cheap min-bet on local pot odds (`required_eq` has no whole-hand commitment term); buries chips with a losing hand, then folds | **Phase 2a** |
| Preflop 4-bet-war then fold (AKo/QQ) | ~15 | 4-bets a hand in the 4-bet *value* range but **not** the jam range; min_raiser always re-raises → forced fold after a 3–5k investment | **Phase 2b** |
| Bluff-raise into a never-folder | ~8 | river bluff-raise at `eq≈0` — `is_calling_station` misclassifies min_raiser (always-raises ⇒ high agg factor) as aggressive, not station-equivalent | **Phase 2c (deferred)** |
| Showdown losses, peak eq > 0.50 | ~19 | got chips in good (mean peak eq 0.74) and lost | **variance — not a leak, do not chase** |

Confirmed: skantbot makes only 18 all-in decisions in 2,803 hands vs
min_raiser, all AA/KK/AKs — stack-off discipline is fine. Buried chips are
~90% postflop (preflop share median 10%).

## Stage-2 scope (advisor-reconciled)

One unifying principle — **don't escalate a pot with a hand you won't
follow through on** — applied at the two sites the trace exposed:

- **Phase 2a** — postflop cumulative-commitment guard: add a whole-hand
  committed-fraction term to `required_eq` so a marginal hand folds
  *early* (decision 2 of an escalating line, not decision 5). Strictly
  additive — only tightens, never loosens, never touches value/raise paths.
- **Phase 2b** — preflop 4-bet-range gate: when facing a 3-bet from an
  opponent whose re-raise frequency is ≈100% (`opp_profile.rfi` far right
  tail — `min_raiser`/`minbet_bot`), do not 4-bet a hand that is not also
  in the jam range. Profile-gated so it does not touch 4-bet ranges vs the
  other 22 opponents.
- **Phase 2c (deferred)** — `is_calling_station` misclassification.
  Deferred: three concurrent fixes would muddy the regression criteria.

2a and 2b share one regression run and **ship together or not at all**.
No sweep — both are structural gates; thresholds chosen by inspection,
round numbers, no tuning. Each is trace-tabled before any code edit.

## UPDATE 2 — trace tables converge all three on ONE root

Tracing the "2a postflop" hands decision-by-decision showed they are **not**
a commitment-leak: every postflop call the bot makes already satisfies
`eq ≥ pot_odds + buffer`, so each call is +EV by immediate pot odds. The
real −EV decision in those hands is a **river value-raise that the bot then
folds to a min-re-raise** — because its equity estimate *collapses* when
min_raiser re-raises.

`aggressor_likely_range` narrows an opponent's assumed range to "strong"
based on postflop raise **count**. min_raiser min-raises every street with
its entire range, so the model narrows it to a value range it does not
have. Verified on 561 raise→faced-reraise pairs vs min_raiser: the bot's eq
estimate drops by **mean 0.16, up to 0.67** when min_raiser re-raises — 20×
the MC noise SD (~0.03 at n_sims 300–600). Not noise.

**All three symptoms share one root:** skantbot's models assume opponents
raise for value / strength.
- `aggressor_likely_range`: raise ⇒ narrow to strong ⇒ eq collapses ⇒ folds
  hands that crush min_raiser's true (any-two) range. (the 2a hands)
- Preflop 4-bet: assumes a 4-bet buys fold equity / faces a capped range —
  min_raiser re-raises any two. (2b)
- `is_calling_station`: keys on passivity; min_raiser is hyper-aggressive so
  is never flagged ⇒ the bot bluffs a never-folder. (2c)

## The honest robustness limitation

Any fix needs a detector for "this opponent raises indiscriminately." That
detector is **itself keyed to the min_raiser archetype** — it makes the bot
robust *to literal min_raiser*, not to "all sorts of random stuff." A real
Day-5 opponent who raises wide-but-not-100% would not trigger it cleanly.

The diagnosis has pivoted three times (eq_override → frog-boil → range
model), each time honestly and trace-driven. The leak "keeps moving"
because min_raiser is pathologically simple and the training pool contains
nothing else like it — it is hard to diagnose against and a fix is unlikely
to transfer to the tournament field. With the ~June 1 deadline, **ship 7.6**
is a legitimate call, not a defeat.

## Decision options (user)

1. **Ship 7.6** — accept the one losing HU matchup (a pure archetype
   unlikely at the real table); spend no more time.
2. **Narrow patch** — skip `aggressor_likely_range` narrowing when the
   opponent's observed raise frequency > ~0.85 and ≥2 postflop raises.
   Low-risk, fixes min_raiser, but an archetype-keyed exploit patch.
3. **Principled fix** — make range-narrowing *proportional to the
   opponent's observed raise frequency* (a 100%-raiser's raise signals
   nothing; a 15%-raiser's raise signals strength). Generalises — the
   correct model — but a larger change to opponent modelling, more
   regression surface.

## Locked success criteria — write once, do not move

1. HU vs `min_raiser`: improvement ≥ +1,400 (≈ 3 SE; −2,493 → ≥ −1,100).
2. HU regression guard (multiple-comparisons-safe): **no** matchup drops
   > 2 SE; **none** flips positive→negative; the 22-matchup aggregate does
   not drop > 1 SE. (A 1-SE per-matchup rule would false-positive ~3–4 of
   22 by noise alone — do not use it.)
3. 6-max: paired-diff vs 7.6 ≥ 0 (no 6-max regression — the 7.6 heldout
   gain lives there).
4. Validator clean; cross-process determinism (`Diff = 0.0` HU vs
   deterministic opponents); bust-suite no regression.
5. **If any criterion fails → ship 7.6.** 7.6 is already +EV vs 22/23 HU
   and the whole 6-max pool; 7.7 is upside only.

## Artifacts

- `harness/skantbot7_6_debug/bot.py` — instrumented 7.6 (probe gated on
  `SKANT_PROBE_DIR`; bit-identical to 7.6 when unset).
- `harness/probe_7_6_analyze.py` — analysis.
- `harness/results/probe_7_6/`, `probe_7_6_hu/` — raw JSONL (not committed).

## Stage 2 — outcome (final)

**Shipped: Phase 2a only.** Option 3 — `aggressor_likely_range` narrowing
scaled by the opponent's observed re-raise frequency. The upstream fix: a
100%-raiser's raise carries no information, a 15%-raiser's signals strength;
range-narrowing is now proportional to that. Degrades exactly to 7.6 when
`reraise_freq ≈ 0.15` (the population prior). Trace-verified against probe
runtime values in `TRACE_2A_LIVE_v77.md`.

**Phase 2b (preflop 4-bet gate) — coded, then stripped, deferred.** A probe
of 7.7 vs `min_raiser` (5,981 hands) recorded the gate firing **0 times**:
Phase 2a busts `min_raiser` in 22–44 hands, before the postflop re-raise
detector converges. The change could not be runtime-verified because it is
never reached in real play — and the methodology does not ship a change no
probe can observe. Stripped from the submission bot (`git checkout HEAD`);
the strip is a no-op (0 fires in the 5,981-hand `min_raiser` probe;
deterministic-opponent CRN shows `Diff = 0.0` in both the 2a+2b and the
stripped HU runs, consistent with no fires elsewhere). Trace in
`TRACE_2B_v77.md`. Revisit in 7.8 only if a real opponent surfaces who
triggers it without busting first.

**Phase 2c (`is_calling_station` misclassification) — deferred.** The 7.7
probe found the canonical 2c spot (river bluff-*raise* at `eq ≈ 0`, raising
over `min_raiser`'s bet) occurs **0 times** in 5,981 hands. The 2c *root*
survives only as river bluff-*bets* (barrels into a never-folder) — but that
is **Mode A** (wide barrelling), already classified "real but the pool
prices it +EV, do not chase". Fixing it means touching `is_calling_station`,
a classifier shared across all 23 matchups. Out of 7.7 scope; belongs with
the deferred Mode A work. Probe: `harness/probe_2c_analyze.py`.

### Final verification — all locked criteria PASS (stripped 2a-only bot)

| # | criterion | result |
|---|-----------|--------|
| 1 | HU `min_raiser` ≥ +1,400 | **+7,455 ± 735** (7.6 −2,100 → 7.7 +5,355), >10 SE |
| 2 | HU regression guard | worst drop −96 (1.23 SE); no flips; 22-matchup aggregate **+532** |
| 3 | 6-max paired-diff ≥ 0 | aggregate **+6,400** (+278/matchup) |
| 4 | validator / determinism / bust-suite | PASS / `Diff = 0.0` (11 det. opps) / 10/10, no regression |

7.7 (Phase 2a) **clearly beats 7.6** — the ship bar is met.
