# Standardized Demo Output Workflow

This workflow turns the four Excel files in `Decision Tree/` into normalized rule
candidates, then creates two demo deliverables:

- `Output Sample/Generated Demo/client_quote_demo.pdf` for customer-facing review.
- `Output Sample/Generated Demo/internal_audit_demo.xlsx` for internal audit and rule traceability.

## One-command Demo Build

```powershell
python .\scripts\run_demo_workflow.py
```

The workflow runs these steps:

1. Normalize all `.xlsx` files from `Decision Tree/`.
2. Write `rules/decision_tree_normalized_rules.json`.
3. Write `rules/decision_tree_rules_needing_review.csv`.
4. Build customer and internal output files under `Output Sample/Generated Demo/`.

## Rule Normalization

Run this step directly when only the rule artifacts need to be refreshed.

```powershell
python .\scripts\normalize_decision_tree_rules.py
```

The normalizer scans product rows, step headers, and note rows from the four
decision tree workbooks. It keeps source workbook, sheet, and cell references so
each candidate can be traced back during review.

Current normalized rule types include:

| Rule type | Meaning |
|---|---|
| `region_allow` | Product or option is limited to listed regions. |
| `region_block` | Product or option is blocked in listed regions. |
| `choose_one` | Exactly one item should be selected from a step or option group. |
| `must_select` | A required product or option selection is called out. |
| `require` | One selection requires another condition or item. |
| `exclude` | Two selections cannot be combined or are unsupported together. |
| `warning` | Customer-visible caution, confirmation, or follow-up. |
| `note` | Informational text preserved for audit or review. |

## Human Review Path

For deterministic rule execution, copy the generated review CSV before editing:

```powershell
Copy-Item .\rules\decision_tree_rules_needing_review.csv .\rules\decision_tree_reviewed_rules.csv
```

Then fill these columns in `rules/decision_tree_reviewed_rules.csv`:

| Column | Expected value |
|---|---|
| `review_decision` | `approve`, `reject`, `info_only`, or `needs_more_context` |
| `final_rule_type` | Confirmed executable rule type |
| `final_effect` | `hard_block`, `warning`, `info`, or `require` |
| `normalized_payload` | JSON payload used by the rule engine or audit output |
| `reviewer`, `reviewed_at`, `review_notes` | Audit trail fields |

Approved rows can be merged with the confirmed rule set:

```powershell
python .\scripts\merge_reviewed_rules.py .\rules\decision_tree_reviewed_rules.csv
```

The merge output is still `rules/merged_rules.json`. Decision-tree review rows
now preserve `product_line`, `option_group`, source workbook, source sheet, and
source cell in the merged rule artifact.

## Standard Output Build

Run this step directly when the normalized JSON already exists:

```powershell
python .\scripts\build_demo_outputs.py
```

Customer PDF content intentionally excludes workbook, sheet, and cell references.
The internal audit Excel includes summary, rule, product, and workflow tabs with
full source traceability.

## Demo Acceptance Checklist

Before showing the demo, confirm:

- All four decision tree workbooks appear in the Summary tab.
- The Rules tab has non-zero `region_allow`, `choose_one`, `must_select`, `require`, and `exclude` candidates.
- The customer PDF has product-line summaries and no source cell references.
- The internal audit workbook keeps `source_workbook`, `source_sheet`, `source_cell`, payload, and review columns.