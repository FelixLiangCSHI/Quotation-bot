# Phase 0 / Subphase 01 - Pilot Scope Definition (One Page)

Date: 2026-09-02
Status: Draft for mentor / PLM / Sales confirmation
Source references: `docs/quotation_bot_mvp_vs_production_architecture.md` (Phase 0), `docs/quotation_bot_chatbot_implementation_flow.md` (Step 0), `quotation_snapshot.json`, `rules/merged_rules.json`.

## 1. Pilot Scenario (Proposed)

> Validate a **DRX-Compass FMT or OTC** quote request: the user describes a quote or configuration question in natural language, the bot extracts the key configuration fields, calls the existing `QuotationRuleEngine`, and returns a clear **valid / invalid / incomplete** result with warnings and explanations.

Recommended first demo case (already covered by regression tests):

> "I Need a compass OTC fit best chest examination"

## 2. In Scope

| Item | Detail |
|---|---|
| Product families | DRX-Compass **FMT** (192 products) and **OTC** (188 products) from `quotation_snapshot.json` |
| Validation types | Product region limits, system compatibility, detector/grid support, generator/tube specs (all implemented in `QuotationRuleEngine`) |
| Rule artifact | `rules/merged_rules.json` (700 confirmed executable rules) |
| Frontend | Local Streamlit demo (`streamlit_app.py`), single session, current-conversation memory only |
| Data source | File-based: `quotation_snapshot.json` + `rules/merged_rules.json` (one snapshot version per demo) |
| Outputs | Extracted fields, validation result (valid / invalid / incomplete), warnings, human-readable explanation, editable quotation preview |

## 3. Out of Scope (for this pilot)

| Excluded item | Reason |
|---|---|
| Production UI (Teams / internal Web App / Copilot Studio) | Production-phase decision (Phase 7) |
| Database, search index, embedding / vector search | Optional later item; file-based data is sufficient |
| The 387 review-needed rules | Blocked on SME review (Phase 8) |
| Cross-session / long-term memory | Requires IT/security retention approval (Phase 5) |
| External SaaS bots (Coze / Dify) as default frontend | Requires approval first |
| LLM as validation authority | Rule engine remains the only validation authority |

## 4. Sample User Questions (Initial Test Set)

1. "I Need a compass OTC fit best chest examination" (baseline demo case)
2. "Quote a DRX-Compass FMT system for the US region with a wireless detector."
3. "Can I sell this Compass configuration in Canada?" (region validation)
4. "Which generator options work with this FMT tube stand?" (compatibility)
5. "I want a Compass OTC with a fixed grid detector - is that supported?" (detector/grid)
6. "Configure a Compass FMT with an 80 kW generator - which tubes are allowed?" (generator/tube spec)
7. "Give me a Compass quote" (incomplete input - bot must ask for missing fields)
8. Sales/PLM to supply 10-20 additional real quote questions with expected answers (owner: Sales / PLM, see Section 6).

## 5. Acceptance Criteria for the Pilot Demo

- The bot answers each in-scope question with extracted fields + rule-engine verdict + explanation.
- Incomplete input produces a specific list of missing required fields, not a generic error.
- No validation decision is made by the LLM alone; every verdict traces to a rule in `rules/merged_rules.json`.
- All existing regression tests continue to pass.

## 6. Confirmations Needed (blocking sign-offs)

| # | Decision | Owner | Status |
|---:|---|---|---|
| 1 | First product family scope: FMT, OTC, or both | PLM / SME | Pending |
| 2 | Most common quote questions (10-20 real cases + expected answers) | Sales / BDM / PLM | Pending |
| 3 | Presentation / demo scope | Mentor / sponsor | Pending |
| 4 | Azure OpenAI endpoint, deployment name, API version, auth, quota | IT / AI platform | Pending (Phase 0 / subphase 02) |
| 5 | Data usage approval: may quote/product/rule data be sent to Azure OpenAI? | IT / security / data owner | Pending (Phase 0 / subphase 03) |
| 6 | Demo runs locally, on internal server, or behind API gateway | IT | Pending (Phase 0 / subphase 04) |

## 7. Next Steps After Sign-off

1. Complete Phase 0 subphases 02-04 (Azure OpenAI access, data usage boundary, run location).
2. Proceed to Phase 1: Beta chat interface flow (question -> extracted fields -> validation -> explanation).
3. Expose `POST /validation/check` as the first internal API (Phase 3/6).
