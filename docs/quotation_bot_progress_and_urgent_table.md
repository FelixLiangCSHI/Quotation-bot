# Quotation Bot Progress and Urgent Items

Date: 2026-07-08  
Source: `rules/rule_review_summary.json`, `rules/confirmed_rules.json`, `rules/merged_rules.json`, `quotation_snapshot.json`, current rule engine tests.

## Progress Summary Table

| Area | What has been completed | Evidence from current JSON / project | Status |
|---|---|---|---|
| Data foundation | Structured quotation data has been prepared and loaded. | `products: 380`, `step_options: 380`, `rule_signals: 984`, `compatibility_matrix: 590`, `detector_grid_matrix: 33`, `generator_tube_matrix: 69` | Completed |
| Rule engine MVP | Core validation paths have been implemented. | Region limit, system compatibility, detector/grid support, generator/tube specs are covered by `QuotationRuleEngine`. | Completed |
| Confirmed executable rules | Confirmed rule artifact has been generated. | `confirmed_rule_count: 700` | Completed |
| Confirmed rule categories | Implemented rule categories have been counted and categorized. | `product_region_allow: 18`, `system_compatibility: 590`, `detector_grid_support: 33`, `generator_tube_spec: 59` | Completed |
| Merged rule artifact | Combined rule artifact exists for confirmed + approved rules. | `rules/merged_rules.json`, `confirmed_rule_count: 700`, `human_approved_rule_count: 0` | Completed |
| Rule review workflow | Candidate rules needing business review have been separated. | `review_rule_count: 387` | Ready for SME review |
| Test coverage | Current rule engine has automated regression checks. | `tests/test_rule_engine.py`, 18 unit tests pass. | Completed |

## Urgent Items Table

| Priority | Urgent item | Current gap | Required support | Owner needed |
|---:|---|---|---|---|
| 1 | SME rule review | `387` candidate rules still need business confirmation. | Confirm approve / reject / info-only / split decisions. | PLM / SME / regional product specialists |
| 2 | Free-text rule normalization | `206` free-text constraints are not safe to execute directly. | Convert approved text into structured rule payloads. | SME + rule owner |
| 3 | Detector / bucky rule decision | `58` detector_bucky_match rules need field mapping. | Confirm detector/bucky business meaning and executable fields. | Product specialist + PLM |
| 4 | Region exclusion decision | `26` region_exclusion rules need allowed/blocked region confirmation. | Decide region_block vs region_allow behavior. | PLM / regional owner |
| 5 | Must-select / choose-one logic | `20` must_select and `16` any_one_of_n rules need workflow scope. | Confirm which step/product group each selection rule applies to. | PLM + sales support |
| 6 | Validation service exposure | Rule engine currently works in Python but is not yet exposed as a callable service. | Wrap existing rule engine as an internal validation service. | Developer / IT API owner |
| 7 | Azure OpenAI access | Reasoning layer requires approved endpoint and data scope. | Confirm Azure OpenAI endpoint, deployment name, API version, auth, quota, data policy. | IT / AI platform / security |
| 8 | Workflow field confirmation | Chatbot needs to know what fields are required before validation. | Confirm FMT/OTC workflow required fields. | PLM + sales support |
| 9 | UAT examples | Beta version needs realistic quote cases. | Provide 10-20 real quote questions and expected answers. | Sales / PLM / SME |

## Rule Review Breakdown

| Review-needed rule type | Count | Required action |
|---|---:|---|
| `free_text_constraint` | 206 | Normalize into deterministic payloads or mark as info-only. |
| `detector_bucky_match` | 58 | Confirm detector/bucky fields and matching logic. |
| `detector_grid_match` | 30 | Confirm whether current detector/grid matrix behavior is enough. |
| `region_exclusion` | 26 | Confirm blocked or allowed regions. |
| `feature_requirement` | 23 | Convert into structured when/then requirement rules. |
| `must_select` | 20 | Confirm required product/option scope. |
| `any_one_of_n` | 16 | Confirm option group and min/max selection rule. |
| `region_only` | 8 | Confirm region part and any extra text. |

## Recommended Message for Reporting

The core backend progress is already meaningful: structured quotation data is available, the rule engine is implemented, 700 confirmed executable rules have been generated, and tests are passing.

The most urgent blockers are not generic coding tasks. The urgent blockers are SME rule review, Azure OpenAI access confirmation, workflow field confirmation, and exposing the existing rule engine as an internal validation service.
