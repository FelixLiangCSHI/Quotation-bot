# Rule Review Workflow

This document explains how to review extracted candidate rules and merge approved
rules with the currently confirmed rule set.

## Decision Tree Demo Workflow

The current demo source is the four Excel workbooks in `Decision Tree/`. Use this
workflow when the decision-tree files are updated and the demo PDF/Excel outputs
need to be regenerated.

```powershell
python .\scripts\run_demo_workflow.py
```

The workflow runs two deterministic steps:

1. Normalize the latest decision-tree workbooks.

```powershell
python .\scripts\normalize_decision_tree_rules.py
```

Outputs:

| File | Purpose |
|---|---|
| `rules/decision_tree_normalized_rules.json` | Standardized product/rule candidate artifact extracted from the four decision-tree workbooks. |
| `rules/decision_tree_rules_needing_review.csv` | Human review spreadsheet with source workbook, sheet, cell, normalized payload, and decision columns. |

2. Build the standardized demo outputs.

```powershell
python .\scripts\build_demo_outputs.py
```

Outputs:

| File | Audience | Purpose |
|---|---|---|
| `Output Sample/Generated Demo/client_quote_demo.pdf` | Customer | Customer-facing quote package summary. It hides internal workbook cell references. |
| `Output Sample/Generated Demo/internal_audit_demo.xlsx` | Internal audit | Traceable workbook with summary, rules, products, workflow, source cells, and review columns. |

The sample files in `Output Sample/` remain the formatting references for the demo
outputs. Generated demo files are written under `Output Sample/Generated Demo/` so
source samples are not overwritten.

## Generated Files

| File | Purpose | Edit by hand? |
|---|---|---|
| `rules/confirmed_rules.json` | Rules already backed by current `QuotationRuleEngine` code paths. | No |
| `rules/rules_needing_review.csv` | Candidate rules that need human review or normalization. | No, use as generated source |
| `rules/reviewed_rules_template.csv` | Copy this to `rules/reviewed_rules.csv` and fill review columns. | Copy first, then edit the copy |
| `rules/rule_review_summary.json` | Counts by confirmed rule type and review rule type. | No |
| `rules/merged_rules.json` | Output from the merge script after review. | No |

## Current Split

| Group | Count | Meaning |
|---|---:|---|
| Confirmed rules | 700 | Already represented by current code paths or structured matrices. |
| Rules needing review | 387 | Extracted signals that are not fully executable yet. |

Confirmed rule types:

| Type | Count |
|---|---:|
| `product_region_allow` | 18 |
| `system_compatibility` | 590 |
| `detector_grid_support` | 33 |
| `generator_tube_spec` | 59 |

Review-needed rule types:

| Type | Count | Why review is needed |
|---|---:|---|
| `free_text_constraint` | 206 | Natural language may contain multiple rules or notes. |
| `region_only` | 8 | Region part may be clear, but extra text may contain more rules. |
| `any_one_of_n` | 16 | Needs option group scope and min/max confirmation. |
| `must_select` | 20 | Needs required option/product scope. |
| `detector_bucky_match` | 58 | Needs detector/bucky field mapping. |
| `detector_grid_match` | 30 | Needs confirmation against current detector/grid matrix behavior. |
| `feature_requirement` | 23 | Needs structured `when` and `then` fields. |
| `region_exclusion` | 26 | Needs explicit blocked/allowed regions. |

## Human Review Steps

1. Regenerate files from the latest snapshot.

```powershell
python .\scripts\export_rule_review_files.py
```

2. Copy the template before editing.

```powershell
Copy-Item .\rules\reviewed_rules_template.csv .\rules\reviewed_rules.csv
```

3. Open `rules/reviewed_rules.csv` in Excel.

4. Review each row and fill these columns:

| Column | Required? | Allowed values / format |
|---|---|---|
| `review_decision` | Yes | `approve`, `reject`, `info_only`, `needs_more_context`, `split` |
| `final_rule_type` | Required if approved | See rule type table below |
| `final_effect` | Required if approved | `hard_block`, `warning`, `info`, `require` |
| `normalized_payload` | Required for most approved rows | JSON object |
| `reviewer` | Recommended | Reviewer name or initials |
| `reviewed_at` | Recommended | Date, e.g. `2026-07-07` |
| `review_notes` | Optional | Any business explanation or unresolved context |

5. Save the reviewed CSV as `rules/reviewed_rules.csv`.

6. Merge approved rows with confirmed rules.

```powershell
python .\scripts\merge_reviewed_rules.py
```

The merge script writes:

```text
rules/merged_rules.json
```

Only rows with `review_decision=approve` are merged. Rejected, info-only, and
needs-more-context rows are left out of executable merged rules.

## Recommended Review Order

Review high-risk and high-value rules first:

1. `region_exclusion` and `region_only`
2. `any_one_of_n` and `must_select`
3. `feature_requirement`
4. `detector_bucky_match` and `detector_grid_match`
5. `free_text_constraint`

## Final Rule Types

| `final_rule_type` | When to use | Example payload |
|---|---|---|
| `region_allow` | Product is only allowed in listed regions. | `{"allowed_regions":["US","Canada"]}` |
| `region_block` | Product is blocked in listed regions. | `{"blocked_regions":["China"]}` |
| `channel_constraint` | Product is limited to sales channel. | `{"allowed_channels":["dealer"]}` |
| `warranty_constraint` | Product requires warranty type. | `{"allowed_warranty":["parts_only"]}` |
| `mount_constraint` | Product requires table/wall/wallstand context. | `{"allowed_mounts":["table"]}` |
| `choose_one` | One option must be selected from a group. | `{"min":1,"max":1,"step_id":"fmt_step_1b"}` |
| `must_select` | A product or option is mandatory. | `{"required_product_ids":["6703656"]}` |
| `require` | If condition is present, another field/value is required. | `{"when":{"product_id":"8620148"},"then":{"detector_type":["Focus"]}}` |
| `exclude` | Two products/options cannot be selected together. | `{"cannot_combine":["product_a","product_b"]}` |
| `detector_bucky_compatibility` | Detector must match bucky requirement. | `{"allowed_detectors":["Focus"],"bucky":"required"}` |
| `detector_grid_support` | Detector/grid relation needs manual override. | `{"grid_id":"8621989","allowed_detectors":["Focus 43C"]}` |
| `warning` | Sales should see a warning, but quote is not blocked. | `{"message":"Confirm with product team before quoting."}` |
| `note` | Informational text only. | `{"message":"Engineering note only."}` |

## Decision Guidelines

Use `approve` only when the row can become a deterministic rule.

Use `reject` when the extracted signal is wrong, obsolete, duplicated, or not a
real business/configuration rule.

Use `info_only` when the text is useful for explanation but should not affect
valid/invalid decisions.

Use `needs_more_context` when the reviewer cannot determine the business meaning
from the row alone.

Use `split` when one row contains multiple rules. In that case, add multiple
manual rows to `rules/reviewed_rules.csv`, give each one a unique `review_id`, and
mark each new row as `approve` with its own `normalized_payload`.

## Merge Behavior

The merge script does not change `confirmed_rules.json`. It creates a new file:

```text
rules/merged_rules.json
```

Merged output structure:

```json
{
  "confirmed_rule_count": 700,
  "human_approved_rule_count": 0,
  "rules": [
    "confirmed rules...",
    "human approved rules..."
  ]
}
```

After reviewers approve rows, `human_approved_rule_count` will increase.

## Important Boundary

`rules/merged_rules.json` is the combined rule artifact. The current rule engine
does not yet execute every future `final_rule_type` automatically. After review,
the next development task is to add handlers in `QuotationRuleEngine` for the
approved structured rule types, starting with the highest-priority types such as
`region_block`, `choose_one`, `must_select`, and `require`.
