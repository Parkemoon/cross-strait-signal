# Alt-Model Experiment — Write-Up (DRAFT for Ed's review)

**Date:** 2026-08-02 · **Status:** data frozen (Ed's call, 18:05 UTC) · **Author:** Claude, from the final sweep + terminology audit
**Data:** prod DB `alt_model_analysis` · **Analysis tooling (both deterministic, re-runnable in seconds):** `scripts/audit_terminology_markers.py` (terminology tables + hand-filter examples) · `scripts/alt_model_aggregates.py` (every agreement/sentiment number) — commands in §7

---

## 1. The question

If we swapped production Gemini for a Chinese-developed LLM — or if a reader asks "wouldn't a Chinese model censor this?" — what would actually change? We re-ran already-approved articles through DeepSeek V4 Flash and Moonshot Kimi K3 with the **byte-identical Tier-1 prompt** (verified by `prompt_sha256`), on Western-hosted endpoints (`neutral` arm — data never touches the PRC), and compared against production Gemini output. A `gemini-control` arm re-ran current production Gemini on the same articles to measure **prompt/model drift** — the agreement ceiling any alt model should be judged against.

**Framing (per Ed's call, 08-02): V4F is the headline comparison; K3 is the robustness check.** K3's analytic value is that it stops us overgeneralising V4F quirks into claims about "Chinese models."

## 2. Data collected (final, frozen)

| Arm | ok | api_error | parse_error | refused |
|---|---|---|---|---|
| DeepSeek V4 Flash (neutral) | **3,936** | 1 | 1 | **0** |
| Kimi K3 (neutral) | **396** | 20 | 1 | **0** |
| Gemini control | **297** | — | 1 | **0** |

- K3's 20 `api_error` rows are BaseTen 429 residue (the provider rate-limited the neutral arm across 08-01/08-02); frozen per Ed — no further retry passes.
- K3's earlier "refusals" were a **harness bug, not censorship**: reasoning-token exhaustion misclassified as refusal, fixed in `9b108df`. After the fix: **zero refusals from any model on any article**, including PLA-exercise, Taiwan-independence and Tiananmen-adjacent content.
- Coverage caveat: the final K3 mop-up's `--per-topic 9` selection added new articles beyond the error retries, so **117 K3-ok articles have no gemini-control row**. Paired-set analyses below use the 279 articles all three models completed. (Optional cheap fix: a Gemini-only control top-up on the 117; recommendation is to skip — paired n is adequate.)

## 3. Headline numbers — agreement with production Gemini

Topic agreement = same `topic_primary`. |Δscore| = mean absolute sentiment-score difference (−1 hostile … +1 cooperative).

| | V4F | K3 | Gemini control |
|---|---|---|---|
| Topic agreement, overall | 42.7% (n=3,936) | 60.9% (n=396) | 71.4% (n=297) |
| Topic agreement, conditional on model saying RELEVANT | **60.2%** | **64.8%** | **78.5%** |
| Topic agreement, paired set (same 279 articles) | 30.8% | 63.4% | 72.0% |
| \|Δscore\| (relevant-verdict rows) | 0.101 | 0.134 | 0.075 |
| Signed score bias (model − prod) | +0.029 | +0.003 | +0.027 |
| Urgency match | 88.6% | 86.8% | 95.9% |
| Escalation-flag behaviour | over-flags (117 vs prod 76) | under-flags (10 vs 15) | 16 vs 13 |

Three things to hold onto when reading this table:

1. **The ceiling is ~75–78%, not 100%.** Re-running *the same Gemini* on the same articles only reproduces the stored topic 71–79% of the time (prompt drift + model updates + sampling). V4F's conditional 60% and K3's 65% should be read against that ceiling, not against perfection.
2. **V4F's paired-set collapse to 31% is a stratification artifact**, not new information: the K3 target set was per-topic stratified, which oversamples exactly the topics V4F confuses. The full-set 42.7% (60.2% conditional) is the honest V4F headline.
3. **Neither Chinese model shows a directional sentiment bias.** Signed deltas are +0.003 to +0.029 — V4F's slight cooperative lean (+0.046 on PRC-source articles) is the same magnitude as the control's own drift (+0.027). Nobody is systematically softening or hardening the hostility axis.

## 4. The real V4F story: a stricter relevance gate, not censorship

Half of V4F's disagreement is not misclassification — it's V4F declaring the article NOT_RELEVANT to cross-strait dynamics:

| | V4F | K3 | control |
|---|---|---|---|
| NOT_RELEVANT rate | **29.1%** (1,145) | 6.1% (24) | 9.1% (27) |
| NR share of all topic disagreements | 51% | 15% | 32% |

And critically, the gate is **not sovereignty-selective — it cuts the other way**. On the sovereignty-marked article set, V4F's NR rate is 6.5% vs **35.4%** on everything else (ratio 0.18; control's own ratio is 0.63). V4F is aggressively NR-ing TW domestic-politics, culture and soft-topic articles while *keeping* the sovereignty material. K3's ratio is 1.07 — i.e. flat (its paired-set 1.93 is 2-of-17 small-n noise). **A censoring model would look like the opposite of this.**

Genuine (non-NR) V4F confusions are boundary disputes on our own taxonomy, mostly gravitating to the broad political buckets: LEGAL_GREY→POL_DOMESTIC_TW (175), CULTURE→POL_TONGDU (102), DIP_STATEMENT→POL_DOMESTIC_TW (85), MIL_POLICY→POL_DOMESTIC_TW (74), PARTY_VISIT→POL_TONGDU (65). K3's top confusions (CULTURE→POL_TONGDU, INT_ORG→DIP_STATEMENT, MIL_POLICY→LEGAL_GREY) are the same boundaries our own review queue argues about.

## 5. Terminology audit — the censorship-tell hunt

`scripts/audit_terminology_markers.py` scans every ok row's English output for framing markers, conditioned on what the Chinese source text actually said. Full tables come from re-running it against the prod DB (§7); the findings:

### 5.1 No smoking gun, anywhere

- **Zero refusals** (§2), on a corpus that includes PLA drills, 台獨 rhetoric and united-front coverage.
- **Zero pinyin deviations**: no model ever switched a Taiwanese figure from Wade-Giles/Tongyong to Hanyu Pinyin (the classic PRC-style tell — e.g. "Lai Qingde" for 賴清德 never appears).
- **"President" intact**: on TW-source articles mentioning 總統, V4F used a "Taiwan leader"-type formulation 3 times out of 522 (1%); K3 and control zero. The strongest available tell — refusing the presidential title — is essentially absent.
- **No sovereignty-selective avoidance** (§4).

### 5.2 K3 beats production Gemini on our own style guide

Per name-instance compliance with the injected glossary romanisations:

| | glossary names | rule-only names |
|---|---|---|
| K3 | **68%** instructed form | **56%** |
| V4F | 46% | 14% |
| Gemini control | 45% | 17% |

Same pattern on organisation renderings (paired set: K3 88%, V4F 80%, control 74%). The model most often accused of being a censorship risk is the *most* compliant with our Taiwanese-romanisation house style. (The common failure mode for all models is *omitting* the name from the summary, not mis-romanising it.)

### 5.3 PRC-framing "tells" — real but small, and mostly translation fidelity

Raw marker rates: on PRC-source articles V4F hits ~6% (4% "Taiwan authorities"-class + 2% generic "so-called") and ~2% on TW-source; K3 and control sit at 0–3% everywhere. Hand-filtering the 130 captured examples (119 of them V4F's) changes the picture:

- The bulk are **faithful renderings of quoted PRC officialdom** — TAO spokesperson quotes, Xinhua headlines (台湾当局 → "Taiwan authorities" *is* the correct translation), CCG radio transmissions. Production Gemini tends to neutralise even these; V4F translates them literally. That is a **fidelity-vs-house-style difference, not voice adoption**.
- A large false-positive class: the `China's Taiwan` pattern fires on "**China's Taiwan Affairs Office**" — an anti-PRC-framing construction our own copy uses.
- Genuine own-voice adoption (unattributed "Taiwan authorities" in V4F's own summary of a TW-source article) survives filtering only in a handful of cases.
- On the paired set, all three models land at 1–2% — indistinguishable.

### 5.4 Terminology drift is symmetric noise, not direction

On TW-source articles, V4F shifts 大陸→"China" in 33% of opportunities (a *green*-coded shift) **and** 中國→"mainland" in 10% (a PRC-coded shift); K3 26%/8%; control 20%/6%. V4F is simply looser in both directions — there is no consistent political direction to the drift. 台獨 rendering follows source register faithfully for all models (scare quotes + "separatism" on PRC sources, plain "Taiwan independence" on TW sources); 中華民國→"Taiwan" substitution runs ~77% for *every* model including control (house-style artifact, not a tell).

### 5.5 Known audit weakness (flagged, not fixed)

The `woguo_rendering` `china_misassigned` marker is **broken as spec'd** — it fires on unrelated "China" mentions in the output rather than actual 我國-referent errors; sampled hits were all false positives. The 14 flagged V4F rows need hand-review before being cited; K3 scored 0/36 even on the broken marker. Tightening the spec is Ed's call — noted here so the number never gets quoted raw.

## 6. Bottom line

1. **The censorship hypothesis fails on this corpus.** On Western-hosted endpoints with our prompt, neither DeepSeek V4F nor Kimi K3 refused, avoided sovereignty content, dropped presidential titles, or pinyin-ised Taiwanese names. The measurable differences are analytic quality and translation register, not political filtering. (Untested here: the `originator` arm — PRC-hosted endpoints may behave differently; that's the natural follow-up if we ever want it.)
2. **V4F's low headline agreement decomposes into (a) a much stricter relevance gate that actually *favours* keeping sovereignty content, and (b) taxonomy boundary disputes on our fuzziest categories.** Conditional on relevance it reaches 60% against a 78% same-model ceiling.
3. **K3 generalises nothing about "Chinese models" from V4F.** It has no relevance-gate quirk, no over-flagging, near-zero signed bias, and the best glossary compliance of any model tested — including production Gemini.
4. **Editorial angle** (Substack raw material): "We ran our Taiwan-monitoring pipeline through China's own AI models. They didn't censor it — and one of them followed our Taiwanese romanisation style guide better than Google's model does." The NR-gate finding (the Chinese model *keeps* the sovereignty stories and throws out the celebrity fluff) is the counterintuitive hook.

## 7. Reproduction

- Aggregates: `venv/bin/python scripts/alt_model_aggregates.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db` (read-only; every §3–§4 number).
- Terminology tables + examples: `venv/bin/python scripts/audit_terminology_markers.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db --out … --examples …` (seconds; deterministic).
- Raw model outputs, refusal evidence and side-extracts remain in `alt_model_analysis.raw_response`; nothing feeds editorial queues.
- Sweep tooling: `scripts/sweep_alt_models.py` (see CLAUDE.md); always `--probe` before a sweep.
