# Alt-model experiment — run notes & provenance

Receipts file for the alt-model experiment's claims about *weights*: which
provider actually served each run, at what precision, when. The write-up
(`ALT_MODEL_EXPERIMENT_WRITEUP.md`) cites this file; sweeps append their
own stanzas automatically.

## Article sweep (context)

The 2026-07/08 article sweeps are documented in the write-up itself (§2
methodology) and per-row in `alt_model_analysis.provider_used` /
`prompt_sha256`. Headline provenance: DeepSeek V4 Flash neutral-arm rows
were served ~99.8% by DeepInfra (13,064/13,083 pre-mop-up), remainder by
DigitalOcean/Cloudflare after the 2026-08-07 whitelist widening.

## Direct-question arm — provider verification 2026-08-12 (pre-run)

Endpoint metadata from `GET openrouter.ai/api/v1/models/<slug>/endpoints`:

- `deepseek/deepseek-v4-flash` — DeepInfra primary (order-preferred), 5
  further Western hosts whitelisted; see `ARMS` in
  `scraper/utils/openrouter.py`.
- `moonshotai/kimi-k3` — Fireworks / Together / BaseTen (BaseTen was
  capacity-flaky during the article sweep; expect provider_used to skew
  Fireworks).
- `deepseek/deepseek-r1-0528` — **DeepInfra serves it at fp4 quantisation**
  (V4F's DeepInfra endpoint runs higher precision). fp4 is aggressive;
  any R1-arm finding must carry this caveat — a refusal-behaviour delta
  between R1-0528@fp4 and the literature's (typically fp8/bf16) serving
  cannot be attributed to weights alone. Original `deepseek/deepseek-r1`
  is only on Novita/Azure (outside our provider set) — 0528 chosen to keep
  zero new provider dependencies, per the brief.
- `gemini-control` — production `gemini-3.1-flash-lite` via the Gemini API.
  Bands A/B/D: `{temperature: 0.1, max_output_tokens: 8000}`, no JSON MIME,
  no thinking override (default model behaviour — the bare-interrogative
  regime). Band C: the production `_TIER1_GEN_CONFIG` (JSON MIME, thinking
  medium), identical to the article sweep's control arm.

Temperature 0.1 is *sent* on every OpenRouter call; endpoints may silently
ignore it. The aggregates' per-cell variance section is the check: high
across-run variance on a cell is the signature of an endpoint running its
own decoding config.

<!-- sweep stanzas append below -->
