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
- `deepseek/deepseek-r1-0528` — **DeepInfra serves it at fp4 quantisation**.
  CORRECTION (live metadata at run time, stanza below): DeepInfra serves
  V4F at fp4 as well — so quantisation is MATCHED across the two DeepSeek
  arms, and a V4F↔R1 behaviour delta on this host cannot be a quantisation
  artifact. The caveat that survives: fp4 is aggressive, and any comparison
  against the literature's (typically fp8/bf16) serving cannot be attributed
  to weights alone. Original `deepseek/deepseek-r1` is only on Novita/Azure
  (outside our provider set) — 0528 chosen to keep zero new provider
  dependencies, per the brief.
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

## Direct-question sweep — 2026-08-12 13:18 UTC
- DB: `/var/www/cross-strait-signal/db/cross_strait_signal.db` · battery `/var/www/cross-strait-signal-staging/scripts/../data/direct_questions.json` (v1) · n=5 per cell · temperature 0.1 (sent; endpoints may ignore — see per-run variance in the aggregates) · endpoint https://openrouter.ai/api/v1/chat/completions + Gemini API (control)
- Planned calls by arm: {'deepseek/deepseek-v4-flash[neutral]': 150, 'moonshotai/kimi-k3[neutral]': 150, 'deepseek/deepseek-r1-0528[neutral]': 150, 'gemini-control[control]': 150}
- Provider endpoint metadata at run time (revision / quantisation):
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DigitalOcean", "name": "DigitalOcean | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-v4-flash-20260423", "quantization": "fp4", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Parasail", "name": "Parasail | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Fireworks", "name": "Fireworks | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Cloudflare", "name": "Cloudflare | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 384000}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "CoreWeave", "name": "CoreWeave | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepSeek", "name": "DeepSeek | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Together", "name": "Together | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1000000}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Moonshot AI", "name": "Moonshot AI | moonshotai/kimi-k3-20260715", "quantization": "mxfp4", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "BaseTen", "name": "BaseTen | moonshotai/kimi-k3-20260715", "quantization": "fp8", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-r1-0528 [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-r1-0528", "quantization": "fp4", "context_length": 163840}
  - gemini-control: `gemini-3.1-flash-lite` via Gemini API; bands A/B/D config `{temperature: 0.1, max_output_tokens: 8000}` (no JSON MIME, no thinking override); band C = production _TIER1_GEN_CONFIG

## Direct-question sweep — 2026-08-13 15:37 UTC
- DB: `/var/www/cross-strait-signal/db/cross_strait_signal.db` · battery `/var/www/cross-strait-signal-staging/scripts/../data/direct_questions.json` (v1) · n=5 per cell · temperature 0.1 (sent; endpoints may ignore — see per-run variance in the aggregates) · endpoint https://openrouter.ai/api/v1/chat/completions + Gemini API (control)
- Planned calls by arm: {'deepseek/deepseek-r1-0528[neutral]': 4}
- Provider endpoint metadata at run time (revision / quantisation):
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DigitalOcean", "name": "DigitalOcean | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-v4-flash-20260423", "quantization": "fp4", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Parasail", "name": "Parasail | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Fireworks", "name": "Fireworks | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Cloudflare", "name": "Cloudflare | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 384000}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "CoreWeave", "name": "CoreWeave | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepSeek", "name": "DeepSeek | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Together", "name": "Together | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1000000}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Moonshot AI", "name": "Moonshot AI | moonshotai/kimi-k3-20260715", "quantization": "mxfp4", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "BaseTen", "name": "BaseTen | moonshotai/kimi-k3-20260715", "quantization": "fp8", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-r1-0528 [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-r1-0528", "quantization": "fp4", "context_length": 163840}
  - gemini-control: `gemini-3.1-flash-lite` via Gemini API; bands A/B/D config `{temperature: 0.1, max_output_tokens: 8000}` (no JSON MIME, no thinking override); band C = production _TIER1_GEN_CONFIG

## Direct-question sweep — 2026-08-13 15:40 UTC
- DB: `/var/www/cross-strait-signal/db/cross_strait_signal.db` · battery `/var/www/cross-strait-signal-staging/scripts/../data/direct_questions.json` (v1) · n=5 per cell · temperature 0.1 (sent; endpoints may ignore — see per-run variance in the aggregates) · endpoint https://openrouter.ai/api/v1/chat/completions + Gemini API (control)
- Planned calls by arm: {'moonshotai/kimi-k3[neutral]': 1}
- Provider endpoint metadata at run time (revision / quantisation):
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DigitalOcean", "name": "DigitalOcean | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-v4-flash-20260423", "quantization": "fp4", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Parasail", "name": "Parasail | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Fireworks", "name": "Fireworks | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "Cloudflare", "name": "Cloudflare | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 384000}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "CoreWeave", "name": "CoreWeave | deepseek/deepseek-v4-flash-20260423", "quantization": "fp8", "context_length": 1048576}
  - deepseek/deepseek-v4-flash [neutral]: {"provider": "DeepSeek", "name": "DeepSeek | deepseek/deepseek-v4-flash-20260423", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Together", "name": "Together | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1000000}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Moonshot AI", "name": "Moonshot AI | moonshotai/kimi-k3-20260715", "quantization": "mxfp4", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "BaseTen", "name": "BaseTen | moonshotai/kimi-k3-20260715", "quantization": "fp8", "context_length": 1048576}
  - moonshotai/kimi-k3 [neutral]: {"provider": "Fireworks", "name": "Fireworks | moonshotai/kimi-k3-20260715", "quantization": "unknown", "context_length": 1048576}
  - deepseek/deepseek-r1-0528 [neutral]: {"provider": "DeepInfra", "name": "DeepInfra | deepseek/deepseek-r1-0528", "quantization": "fp4", "context_length": 163840}
  - gemini-control: `gemini-3.1-flash-lite` via Gemini API; bands A/B/D config `{temperature: 0.1, max_output_tokens: 8000}` (no JSON MIME, no thinking override); band C = production _TIER1_GEN_CONFIG
