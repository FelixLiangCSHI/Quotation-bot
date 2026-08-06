from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_loader import load_snapshot  # noqa: E402


OUTPUT_DIR = ROOT / "rules"
SNAPSHOT_NAME = "quotation_snapshot.json"

REGION_ALIASES = {
    "c": "canada",
    "ca": "canada",
    "canada": "canada",
    "cn": "china",
    "china": "china",
    "prc": "china",
    "u.s.": "us",
    "usa": "us",
    "united states": "us",
    "us": "us",
}

REVIEW_REASONS = {
    "any_one_of_n": "not_yet_implemented_option_cardinality",
    "detector_bucky_match": "not_yet_implemented_detector_bucky_check",
    "detector_grid_match": "candidate_detector_grid_rule_needs_confirmation",
    "feature_requirement": "not_yet_implemented_requirement_rule",
    "free_text_constraint": "natural_language_constraint_needs_normalization",
    "must_select": "not_yet_implemented_required_selection",
    "region_exclusion": "not_yet_implemented_region_block",
    "region_only": "region_part_implemented_review_extra_text",
}

FULLY_IMPLEMENTED_RULE_SIGNAL_TYPES = {
    "matrix_not_supported",
    "matrix_support",
}

REVIEW_COLUMNS = [
    "review_id",
    "rule_id",
    "rule_type",
    "current_review_status",
    "engine_status",
    "review_reason",
    "product_id",
    "step_id",
    "applies_to_step_id",
    "regions",
    "strength",
    "confidence",
    "message",
    "source_sheet",
    "source_cell",
    "review_decision",
    "final_rule_type",
    "final_effect",
    "normalized_payload",
    "reviewer",
    "reviewed_at",
    "review_notes",
]


def main() -> None:
    snapshot = load_snapshot(ROOT / SNAPSHOT_NAME)
    OUTPUT_DIR.mkdir(exist_ok=True)

    confirmed_rules = build_confirmed_rules(snapshot)
    review_rows = build_review_rows(snapshot)

    write_json(
        OUTPUT_DIR / "confirmed_rules.json",
        {
            "generated_from": SNAPSHOT_NAME,
            "description": (
                "Rules already backed by current code paths in QuotationRuleEngine. "
                "This file is regenerated from the snapshot."
            ),
            "counts_by_type": dict(Counter(rule["type"] for rule in confirmed_rules)),
            "rules": confirmed_rules,
        },
    )
    write_review_csv(OUTPUT_DIR / "rules_needing_review.csv", review_rows)
    write_review_csv(OUTPUT_DIR / "reviewed_rules_template.csv", review_rows)
    write_json(
        OUTPUT_DIR / "rule_review_summary.json",
        {
            "generated_from": SNAPSHOT_NAME,
            "confirmed_rule_count": len(confirmed_rules),
            "confirmed_counts_by_type": dict(
                Counter(rule["type"] for rule in confirmed_rules)
            ),
            "review_rule_count": len(review_rows),
            "review_counts_by_type": dict(Counter(row["rule_type"] for row in review_rows)),
            "review_counts_by_reason": dict(
                Counter(row["review_reason"] for row in review_rows)
            ),
        },
    )

    print(f"confirmed_rules={len(confirmed_rules)}")
    print(f"rules_needing_review={len(review_rows)}")
    print(f"output_dir={OUTPUT_DIR}")


def build_confirmed_rules(snapshot: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    rules.extend(build_confirmed_region_rules(snapshot))
    rules.extend(build_confirmed_system_rules(snapshot))
    rules.extend(build_confirmed_detector_grid_rules(snapshot))
    rules.extend(build_confirmed_generator_tube_rules(snapshot))
    return rules


def build_confirmed_region_rules(snapshot: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    for signal in snapshot.rule_signals:
        allowed_regions = allowed_regions_from_signal(signal)
        if not signal.product_id or not allowed_regions:
            continue
        key = (signal.product_id, tuple(sorted(allowed_regions)), signal.message)
        if key in seen:
            continue
        seen.add(key)
        rules.append(
            {
                "id": f"confirmed:product_region_allow:{len(rules) + 1:04d}",
                "type": "product_region_allow",
                "effect": "hard_block_outside_allowed_regions",
                "source_type": "rule_signal",
                "original_rule_id": signal.rule_id,
                "product_id": signal.product_id,
                "allowed_regions": sorted(allowed_regions),
                "message": signal.message,
                "source": signal.source,
            }
        )
    return rules


def build_confirmed_system_rules(snapshot: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(snapshot.compatibility_matrix, start=1):
        status = item.status.casefold().strip()
        if status == "not_supported":
            effect = "hard_block"
        elif status == "supported":
            effect = "allow"
        else:
            effect = "warning"
        rules.append(
            {
                "id": f"confirmed:system_compatibility:{index:04d}",
                "type": "system_compatibility",
                "effect": effect,
                "source_type": "compatibility_matrix",
                "matrix_name": item.matrix_name,
                "system_family": item.system_family,
                "acquisition_type": item.acquisition_type,
                "tube_stand_id": item.tube_stand_id,
                "tube_stand_name": item.tube_stand_name,
                "wallstand_id": item.wallstand_id,
                "wallstand_name": item.wallstand_name,
                "table_id": item.table_id,
                "table_name": item.table_name,
                "status": item.status,
                "signal_text": item.signal_text,
                "remark": item.remark,
                "source": item.source,
            }
        )
    return rules


def build_confirmed_detector_grid_rules(snapshot: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(snapshot.detector_grid_supports, start=1):
        rules.append(
            {
                "id": f"confirmed:detector_grid_support:{index:04d}",
                "type": "detector_grid_support",
                "effect": "allow",
                "source_type": "detector_grid_matrix",
                "grid_id": item.grid_id,
                "grid_description": item.grid_description,
                "support_kind": item.support_kind,
                "support_name": item.support_name,
                "support_value": item.support_value,
                "source": item.source,
            }
        )
    return rules


def build_confirmed_generator_tube_rules(snapshot: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(snapshot.generator_tube_specs, start=1):
        rules.append(
            {
                "id": f"confirmed:generator_tube_spec:{index:04d}",
                "type": "generator_tube_spec",
                "effect": "info",
                "source_type": "generator_tube_matrix",
                "generator": item.generator,
                "spec_category": item.spec_category,
                "tube_spec": item.tube_spec,
                "value": item.value,
                "source": item.source,
            }
        )
    return rules


def build_review_rows(snapshot: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for signal in snapshot.rule_signals:
        if not needs_human_review(signal):
            continue
        rows.append(review_row(signal, len(rows) + 1))
    return rows


def needs_human_review(signal: Any) -> bool:
    rule_type = signal.rule_type
    if rule_type in FULLY_IMPLEMENTED_RULE_SIGNAL_TYPES:
        return False
    return True


def review_row(signal: Any, index: int) -> dict[str, str]:
    source = signal.source or {}
    reason = REVIEW_REASONS.get(signal.rule_type, "needs_review")
    engine_status = "not_implemented"
    if allowed_regions_from_signal(signal):
        engine_status = "partially_implemented_region_rule"
    elif signal.rule_type == "detector_grid_match":
        engine_status = "partially_implemented_detector_grid_matrix"

    return {
        "review_id": f"review:{index:04d}",
        "rule_id": signal.rule_id,
        "rule_type": signal.rule_type,
        "current_review_status": signal.review_status,
        "engine_status": engine_status,
        "review_reason": reason,
        "product_id": signal.product_id or "",
        "step_id": signal.step_id or "",
        "applies_to_step_id": signal.applies_to_step_id or "",
        "regions": ";".join(signal.regions),
        "strength": signal.strength,
        "confidence": str(signal.confidence),
        "message": signal.message,
        "source_sheet": str(source.get("sheet") or ""),
        "source_cell": str(source.get("cell") or ""),
        "review_decision": "",
        "final_rule_type": proposed_rule_type(signal.rule_type),
        "final_effect": proposed_effect(signal.rule_type),
        "normalized_payload": "",
        "reviewer": "",
        "reviewed_at": "",
        "review_notes": "",
    }


def proposed_rule_type(rule_type: str) -> str:
    return {
        "any_one_of_n": "choose_one",
        "detector_bucky_match": "detector_bucky_compatibility",
        "detector_grid_match": "detector_grid_support",
        "feature_requirement": "require",
        "free_text_constraint": "review_needed",
        "must_select": "must_select",
        "region_exclusion": "region_block",
        "region_only": "region_allow",
    }.get(rule_type, "review_needed")


def proposed_effect(rule_type: str) -> str:
    return {
        "any_one_of_n": "hard_block",
        "detector_bucky_match": "hard_block",
        "detector_grid_match": "hard_block",
        "feature_requirement": "hard_block",
        "free_text_constraint": "review_needed",
        "must_select": "hard_block",
        "region_exclusion": "hard_block",
        "region_only": "hard_block",
    }.get(rule_type, "review_needed")


def allowed_regions_from_signal(signal: Any) -> set[str]:
    if not signal.regions:
        return set()
    if "only" not in signal.message.casefold() and signal.rule_type != "region_only":
        return set()
    return {normalize_region(region) for region in signal.regions}


def normalize_region(region: str) -> str:
    normalized = region.casefold().strip()
    return REGION_ALIASES.get(normalized, normalized)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_review_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
