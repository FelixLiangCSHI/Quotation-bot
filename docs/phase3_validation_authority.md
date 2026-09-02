# Phase 3 - Rule Engine as Validation Authority (Execution Log)

Status: **Complete - `POST /validation/check` live and regression-tested.**

## Subphase execution

| Subphase | Roadmap item | Implementation | Status |
|---:|---|---|---|
| 01 | Keep using `QuotationRuleEngine` for deterministic validation | New `POST /validation/check` endpoint (`app/api.py`) wraps `engine.check_configuration()` directly - no LLM in the validation path, response always reports `validation_authority: QuotationRuleEngine` | Done |
| 02 | Load `quotation_snapshot.json` and `rules/merged_rules.json` | Snapshot was already loaded by `QuoteRecommender`; added `load_merged_rules()` to `app/data_loader.py`, and every validation response carries `rule_artifacts` metadata (snapshot products/rule_signals + 700 confirmed rules) | Done |
| 03 | Convert parsed user input into structured validation input | `_resolve_validation_input()` - natural-language `message` is parsed via `parse_quote_request()` into product ids / region / system_family / acquisition_type; explicit structured `fields` (all 13 `check_configuration` parameters) always override parsed values; product ids from both sources are merged | Done |
| 04 | Return `valid`, `invalid`, `incomplete`, warning, and info results | Response exposes `status` (valid/invalid/incomplete), full `issues[]` with severity error/warning/info + rule ids + source evidence, `missing_fields[]`, and a `summary` count per severity | Done |

## Endpoint contract

```http
POST /validation/check
Content-Type: application/json

{
  "message": "Can I quote product 6703656 for the EU?",   // optional
  "fields": {                                              // optional, overrides message
    "product_ids": ["6703656"],
    "region": "us",
    "system_family": "FMT",
    "acquisition_type": "digital",
    "tube_stand_id": null, "wallstand_id": null, "table_id": null,
    "grid_id": null, "grid_position": null, "detector_type": null,
    "generator": null, "tube_spec": null, "spec_category": null
  }
}
```

Response:

```json
{
  "status": "invalid",
  "issues": [{"severity": "error", "code": "region_not_allowed", "message": "...", "rule_id": "...", "source": {...}}],
  "missing_fields": [],
  "summary": {"errors": 1, "warnings": 0, "infos": 0},
  "resolved_input": {"product_ids": ["6703656"], "region": "eu", ...},
  "rule_artifacts": {
    "quotation_snapshot": {"products": 191, "rule_signals": 984},
    "merged_rules": {"confirmed_rule_count": 700, "human_approved_rule_count": 0}
  },
  "validation_authority": "QuotationRuleEngine"
}
```

Errors: `422` when neither message nor any field is provided, when the message
is blank, or when the region is unsupported.

## Test results (Phase 3 acceptance)

New suite `tests/test_validation_api.py` (13 tests):

| Case | Expectation | Result |
|---|---|---|
| Message only, 6703656 in EU | `invalid` + `region_not_allowed`, 1 error | Pass |
| Structured fields, 6703656 in US | `valid`, zero issues | Pass |
| Message says EU, fields say US | fields win → `valid`, resolved region `us` | Pass |
| Product without region | `incomplete` + `missing_fields: [region]` | Pass |
| Unknown product id 9999999 | `invalid` with issue code | Pass |
| Empty body / blank message | 422 | Pass |
| Unsupported region `mars` | 422 | Pass |
| Product ids merged from message + fields | deduplicated union | Pass |
| Rule artifacts metadata | 700 confirmed rules, snapshot counts > 0 | Pass |
| Detector/grid fields accepted | resolved input carries grid fields | Pass |
| `load_merged_rules()` happy path + bad shape | 700 rules / ValueError | Pass |

Full regression: **165 tests + 40 subtests pass** (was 152 before Phase 3).

## Notes

- This is the first productionized endpoint per the roadmap ("This is the
  first endpoint that should be productionized").
- The Phase 2 reasoning layer is deliberately **not** wired into
  `/validation/check` - validation input conversion is purely deterministic.
  If LLM-assisted extraction is wanted for this endpoint later, it must stay
  supplement-only, mirroring `/recommend`.
- Remaining organizational items (unchanged): PLM/SME business validation of
  issue messages, and QA/sales-provided regression cases from real quotes.
