# skantbot 7.7 Phase 2b — preflop 4-bet-range gate (trace table)

> **STATUS: NOT SHIPPED — deferred to 7.8.** Phase 2b was coded into both
> bots, then stripped from the submission bot. A 5,981-hand probe of 7.7 vs
> min_raiser recorded the gate firing **0 times** — Phase 2a busts min_raiser
> before the detector converges, so the change can never be runtime-verified
> in real play. The methodology does not ship an unobservable change. See the
> "Stage 2 — outcome" section of `STAGE1_DIAGNOSIS_v77.md`.

## The bug

When facing a 3-bet, the bot 4-bets hands in `FOURBET_VALUE_FREQS` (QQ+, AKs, AKo).
Against a normal opponent, this is correct — a 4-bet buys fold equity or caps
the opponent's continuing range.

Against min_raiser (who re-raises 100% of the time), a 4-bet just escalates
the pot. min_raiser will 5-bet any two cards, and if the bot's hand is NOT in
the jam range, it folds — losing the 4-bet investment (~1,350 chips).

**The gap:** AKo is in `FOURBET_VALUE_FREQS` but NOT in the jam range
(`TIGHT_MONSTERS = AA, KK, QQ, AKs`). So the bot 4-bets AKo, min_raiser
5-bets, bot folds AKo.

## Trace 1 — A5s (in 4-bet range, not in jam range)

From probe data, HU vs min_raiser, hand with A5s:

### 7.6 behaviour (decision flow):

| # | action | scenario | hand | owed | pot | stack | decision driver |
|---|--------|----------|------|------|-----|-------|-----------------|
| 1 | raise  | open     | A5s  | 50   | 150 | 9349  | opens SB |
| 2 | (min_raiser 3-bets to 503) | — | — | — | — | — | — |
| 3 | raise  | face_3bet_as_raiser | A5s | 101 | 503 | 9198 | A5s is NOT in FOURBET_VALUE (QQ+,AK) → should NOT fire, but old probe might have different ranges |
| 4 | (min_raiser 5-bets to 2764) | — | — | — | — | — | — |
| 5 | fold   | face_5bet_as_raiser | A5s | 1048 | 3748 | 8049 | A5s not in jam range → fold |

**Loss: 1,350 chips** (the 4-bet investment).

Wait — A5s is NOT in `FOURBET_VALUE_FREQS` (QQ+, AKs, AKo). Let me re-check
the probe data. The issue is the bot DOES 4-bet A5s in the trace, which means
either:
1. The bluff branch fired (line 1335-1338: `FOURBET_BLUFF_FREQS`)
2. The probe was from an older version with a wider 4-bet range

Let me trace a clearer example with AKo.

## Trace 2 — AKo (clearly in 4-bet range, not in jam range)

AKo is in `FOURBET_VALUE_FREQS` (line 334) but NOT in `TIGHT_MONSTERS`
(jam range at line 1314 is AA/KK/QQ/AKs). So:

### 7.6 behaviour:

| # | street | action | hand | scenario | owed | pot | stack | note |
|---|--------|--------|------|----------|------|-----|-------|------|
| 1 | preflop | raise | AKo | open | 50 | 150 | 9950 | opens |
| 2 | preflop | (opp 3-bets to 503) | — | — | — | — | — | — |
| 3 | preflop | raise | AKo | face_3bet_as_raiser | 101 | 503 | 9799 | 4-bets AKo (in FOURBET_VALUE) |
| 4 | preflop | (opp 5-bets to 2764) | — | — | — | — | — | — |
| 5 | preflop | fold | AKo | face_5bet_as_raiser | 1048 | 3748 | 8649 | folds AKo (not in jam range) |

**Loss: 1,350 chips.**

### 7.7 behaviour (with Phase 2b gate):

| # | street | action | hand | scenario | owed | pot | stack | note |
|---|--------|--------|------|----------|------|-----|-------|------|
| 1 | preflop | raise | AKo | open | 50 | 150 | 9950 | opens |
| 2 | preflop | (opp 3-bets to 503) | — | — | — | — | — | — |
| 3 | preflop | **call** | AKo | face_3bet_as_raiser | 101 | 503 | 9799 | **GATE: opp reraise_freq > 0.35, AKo not in jam range → `skip_fourbet=True` → falls through to the value-call branch (AKo ∈ {JJ,TT,AKo,AQs}, owed 101 ≤ stack·call_thresh) → calls the 3-bet** |
| 4 | flop+ | — | AKo | — | — | — | — | sees a flop; Phase 2a's reraise-scaled range now estimates AKo's equity correctly vs min_raiser's random range |

**Investment: 101 chips to see a flop** (vs 1,350 for the old 4-bet line).

The gate does **not** make AKo fold — it sits *after* the jam-or-fold exits
(4-bet-commit check, shallow-stack check), so on a deep stack the only thing it
suppresses is the 4-bet escalation. AKo then takes the standard value-call line.
Calling 101 to see a flop with a hand that has real equity vs a random range is
strictly better than 4-betting to ~1,350 and folding to the 5-bet.

Net savings vs the old 4-bet-then-fold line: ~1,250 chips per occurrence.

## The fix (Phase 2b)

Before the 4-bet decision (bot.py line 1325-1335), add a gate. Actual
implementation (`skip_fourbet` flag, checked by both the value-4-bet and
bluff-4-bet blocks):

```python
# Phase 2b gate: vs indiscriminate re-raisers (reraise_freq > 0.35),
# only 4-bet jam-range hands.
skip_fourbet = False
if opp_profile is not None:
    fb = opp_profile.faced_bet_postflop
    rwf = opp_profile.raised_when_faced_postflop
    reraise_freq = (rwf + 3.0) / (fb + 20.0)
    if reraise_freq > 0.35:
        jam_hand = (lookup_freq(FIVEBET_FREQS, hand) > 0 or hand in TIGHT_MONSTERS)
        if not jam_hand:
            skip_fourbet = True
```

When `skip_fourbet` is True, both the value 4-bet (`if not skip_fourbet:`) and
the bluff 4-bet (`if not facing_maniac and not skip_fourbet and ip:`) are
skipped; execution falls through to the existing value-call / check / fold
logic. Nothing is forced to fold.

**Detector choice:** the original draft used `pfr + three_bet > 0.85`, but
those stats converge too slowly (~100+ hands) — Phase 2a busts min_raiser long
before they cross the threshold. The shipped gate reuses Phase 2a's
`reraise_freq` stat (Bayesian, prior 0.15), which converges after ~20-30
faced-bet observations. `reraise_freq > 0.35` is the far-right tail —
min_raiser/minbet_bot converge to ≈0.40-0.69; normal opponents sit at ≈0.15.

**Jam range:** `FIVEBET_FREQS` (KK+, AKs) OR `TIGHT_MONSTERS` (AA/KK/QQ/AKs).
This is the exact same condition used at line 1314 to decide whether to jam
when a 4-bet would commit too much. The gate just applies it earlier.

## Expected impact

From Stage 1 diagnosis: ~15 big-loss hands were "preflop 4-bet-war then fold"
(mean loss ~2,200 chips each). If the fix prevents 15 * 1,300 = **+19,500
chips** across 200 hands, that's **+98 chips/hand** in the affected hands.

But the overall impact is smaller: 15 / 2803 hands = 0.5% occurrence rate.
Expected contribution to the min_raiser matchup: **+98 * 0.005 ≈ +500 chips/match**.

Phase 2a alone gave +7,033. Phase 2b is expected to add another +500–1,000.

## Actual implementation note

Phase 2a was so effective that HU matches vs min_raiser now end in ~22-44
hands (min_raiser busts). This is BEFORE the Phase 2b gate has enough
observations to activate (reraise_freq converges after ~20-30 faced-bet
observations). So the gate rarely fires in practice — 2a is doing the heavy
lifting.

However, the gate is still correct insurance: if a longer match occurs (6-max,
or a lucky min_raiser run in HU), the gate prevents the 4-bet-then-fold trap
once the stat converges. It's a defensive layer that costs nothing (only
narrows 4-bet range, never widens) and cannot cause regressions.

## Regression risk

The gate only fires when `reraise_freq > 0.35`. Normal opponents converge to
`reraise_freq ≈ 0.15` (population prior) → gate does not fire. Only
min_raiser/minbet_bot, which re-raise faced bets at ≈0.40-0.69, trigger it.
The gate is profile-gated and only narrows the 4-bet range, never widens it →
cannot cause a leak against normal opponents. CRN self-compare confirms
Diff = +0.0 ± 0.0 against all 23 opponents (deterministic, no code-path change
when the gate doesn't fire).

## Next step

Code the gate, instrument the debug bot to capture when it fires, run a probe
vs min_raiser to verify:
1. AKo now folds instead of 4-betting
2. AA/KK/QQ/AKs still 4-bet (jam range preserved)
3. No change in decisions vs normal opponents (gate doesn't fire)

Then run the full regression suite.
