# Phase 2 - Connect Reasoning Layer (Execution Log)

Status: **Integration port reserved and verified with mocks - waiting for the
enterprise DeepSeek-v4-pro credentials to go live.**

## Decision update

The roadmap originally recommended Azure OpenAI. The organization has since
provided an **enterprise DeepSeek-v4-pro API** (OpenAI-compatible), so the
reasoning layer now targets that endpoint. The Phase 0 data-usage boundary
(`docs/phase0_data_usage_approval.md`) applies unchanged: only the user's
question text and per-turn extracted fields are sent - never product JSON
files, pricing, or workbook comments.

## What was built

| Subphase | Roadmap item | Implementation | Status |
|---:|---|---|---|
| 01 | Use LLM for intent extraction | `LLMClient.extract_fields()` in `app/llm.py` - closed-vocabulary sanitization drops any hallucinated value | Done (mock-verified) |
| 02 | Use LLM for field extraction | `_apply_llm_extraction()` in `app/api.py` - LLM only fills fields the deterministic parser missed; deterministic extraction always wins | Done (mock-verified) |
| 03 | Use LLM for explanation wording | `LLMClient.polish_explanation()` + `_apply_llm_wording()` - polish is optional; deterministic answer kept on any failure | Done (mock-verified) |
| 04 | Do **not** use LLM as final validation authority | Validation stays 100% in `QuotationRuleEngine`; response `reasoning.validation_authority` always reports it | Done (enforced by design + tests) |

## Integration port (reserved for the enterprise API)

- Client: `app/llm.py` - stdlib-only OpenAI-compatible `POST {base}/chat/completions`.
- Configuration (see `.env.example`); the layer is **disabled until both the
  base URL and key are set**, and the bot works fully without it:

| Variable | Meaning | Default |
|---|---|---|
| `LLM_API_BASE` (or `DEEPSEEK_API_BASE`) | OpenAI-compatible base URL from the AI platform | empty = disabled |
| `LLM_API_KEY` (or `DEEPSEEK_API_KEY`) | Enterprise API key (never committed) | empty = disabled |
| `LLM_MODEL` | Model / deployment name | `deepseek-v4-pro` |
| `LLM_TIMEOUT_SECONDS` | Per-request timeout | `15` |

- Diagnostics: `GET /llm/status` reports enabled/provider/model and the fixed
  role statement ("intent/field extraction and explanation wording only").
- Every `/recommend` response now carries a `reasoning` block:
  `llm_enabled`, `llm_fields_used`, `llm_wording_used`,
  `validation_authority: QuotationRuleEngine`.

## Safety guarantees (tested in `tests/test_llm.py`)

1. **Graceful degradation** - no config, network error, timeout, or malformed
   reply all fall back to the deterministic pipeline (answer still produced).
2. **No override** - LLM extraction can only fill `None` fields; it can never
   change a value the regex parser already found.
3. **Closed vocabularies** - extracted region/system_family/acquisition_type
   are validated against allowed sets; product ids must be 7-digit; anything
   else is dropped before reaching the rule engine.
4. **Verdict integrity** - wording polish rewrites text only; the structured
   `recommendation.validation` verdict is computed before and independent of
   the LLM.

## Verification

- `tests/test_llm.py`: 20 new tests (config, client failure modes,
  sanitization, JSON parsing, status endpoint, API supplement/polish/fallback
  paths) - all mocked, no network.
- Full suite: **152 tests + 40 subtests pass**.
- `GET /llm/status` without config → `{"enabled": false, ...}` (disabled slot).

## Go-live checklist (when credentials arrive)

1. Copy `.env.example` → `.env`, fill `LLM_API_BASE` + `LLM_API_KEY`
   (and `LLM_MODEL` if the deployment name differs from `deepseek-v4-pro`).
2. Export the variables into the API process environment and restart uvicorn.
3. Confirm `GET /llm/status` returns `enabled: true`.
4. Re-run the pilot questions from `docs/phase0_pilot_scope.md` and compare
   answers with the deterministic baseline.
5. Verify no prohibited data appears in outbound prompts (spot-check logs).
