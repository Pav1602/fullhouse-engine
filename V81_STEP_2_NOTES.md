# V81 Step 2 — Per-opp range narrowing (#2) — REJECTED, ROLLED BACK

## Outcome

Step 2 was implemented per plan §6.3, paper-hand-verified (7/7), and ran
the §6.5 validation gates. Gates D and E **failed dramatically**. Per the
deterministic failure rule from the V81 plan amendment, #2 has been
**rolled back entirely**; skantbot8 is restored to v81-step1-bet-sizing
state (= 7.13 + #1 only).

## Gate results

- A (CRN): PASS
- B (min_raiser HU): +7600 ± 452, Δ=+400 (PASS, slight improvement)
- F (maniac/super_nit HU preservation): PASS (maniac_aggro +400, super_nit
  +0 — no regression)
- **D (TRAIN_EXPANDED_V81): FAIL**. avg Δ = -7 chips/opp, worst opp
  ref_bot_2 Δ=-28 σ=-2.04 (>2σ regression). Plan threshold "net positive,
  magnitude > 100" was not met.
- **E (UNSEEN_VALIDATION_V81): FAIL DRAMATICALLY**.
  avg Δ = -121 chips/opp, sum -969. **5 of 8 opps with >2σ regression**:
  chatgpt-7 (-2.71σ), claude-9 (-2.74σ), gemini-1 (-2.09σ), limp_machine
  (-2.80σ), super_nit (-2.49σ).

## Root cause — aggression_factor mis-classifies LLM tight-folders as "maniacs"

The plan's §6.1 pre-diagnostic ("verify opp_profile.aggression_factor
differentiates nit/maniac") was SKIPPED in this run. That skip cost a step.

From the V81 pool signature (`harness/results/pool_signature_v81.json`):

- chatgpt-7: VPIP 14%, **AF 3.15** → my code classified MANIAC (af>1.5)
  → narrow LESS → I treat their bet as random → over-call → big loss.
- claude-9: VPIP 3%, **AF 4.19** → MANIAC again, same failure mode.
- claude-4: VPIP 17%, **AF 0.04** → NIT correctly → narrow MORE.

aggression_factor = postflop_bets_raises / postflop_calls. A bot that
**folds most postflop hands but bets the rest** has near-zero
postflop_calls and arbitrary postflop_bets_raises → AF blows up to high
values. That's LLM-tight-folder behavior, not maniac behavior.

A proper nit/maniac classification needs BOTH VPIP and AF axes
(or actively use postflop_calls + postflop_bets_raises as a denominator-
aware combined metric). One-axis classification fails on this pool.

## Files changed (rolled back)

- `bots/skantbot8/bot.py` — reverted to v81-step1-bet-sizing
- `harness/skantbot8_dev/bot.py` — reverted to v81-step1-bet-sizing
- `_paper_hands_skb8_step2.py` — kept (audit trail; tests were correct,
  the bot's mis-classification on the actual heldout pool was the
  problem)

## Implication for V81 sweep (Step 5)

The sweep param space MUST NOT include #2 knobs
(`skb8_nit_af_threshold`, `skb8_maniac_af_threshold`,
`skb8_min_hands_per_opp`). Including them would re-enable the broken
modifier path through TPE-tuned thresholds — same overfitting risk that
V80b had with its 60-dim space.

## Deferred to V82

A proper per-opp range modifier requires a multi-axis opponent classifier
(VPIP + AF + bet-size-distribution). That's a research project, not a
1-week sweep tweak. Defer alongside #3 (calibrated equity model) and #5
(forward-look).
