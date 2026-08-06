from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RULE_DIR = ROOT / "rules"
CONFIRMED_PATH = RULE_DIR / "confirmed_rules.json"
DEFAULT_REVIEWED_PATH = RULE_DIR / "reviewed_rules.csv"
FALLBACK_REVIEWED_PATH = RULE_DIR / "rules_needing_review.csv"
MERGED_PATH = RULE_DIR / "merged_rules.json"

APPROVE_VALUES = {"approve", "approved", "yes", "y"}


def main() -> None:
    reviewed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REVIEWED_PATH
    if not reviewed_path.exists():
        reviewed_path = FALLBACK_REVIEWED_PATH

    confirmed = read_json(CONFIRMED_PATH)
    review_rows = read_review_csv(reviewed_path)
    reviewed_rules = [build_reviewed_rule(row) for row in review_rows if is_approved(row)]

    merged = {
        "generated_from": {
            "confirmed_rules": str(CONFIRMED_PATH.relative_to(ROOT)),
            "reviewed_rules": str(reviewed_path.relative_to(ROOT)),
        },
        "description": (
            "Confirmed rules plus human-approved structured rules. "
            "Only rows with review_decision=approve are merged."
        ),
        "confirmed_rule_count": len(confirmed.get("rules", [])),
        "human_approved_rule_count": len(reviewed_rules),
        "rules": confirmed.get("rules", []) + reviewed_rules,
    }
    write_json(MERGED_PATH, merged)
    print(f"confirmed_rules={merged['confirmed_rule_count']}")
    print(f"human_approved_rules={merged['human_approved_rule_count']}")
    print(f"merged_rules={MERGED_PATH}")


def is_approved(row: dict[str, str]) -> bool:
    return row.get("review_decision", "").casefold().strip() in APPROVE_VALUES


def build_reviewed_rule(row: dict[str, str]) -> dict[str, Any]:
    payload_text = row.get("normalized_payload", "").strip()
    payload: dict[str, Any] = {}
    if payload_text:
        payload = json.loads(payload_text)

    return {
        "id": f"human:{row.get('review_id', '').replace(':', '_')}",
        "type": row.get("final_rule_type") or "reviewed_rule",
        "effect": row.get("final_effect") or "hard_block",
        "source_type": "human_review",
        "original_rule_id": row.get("rule_id", ""),
        "product_line": row.get("product_line", ""),
        "product_id": row.get("product_id", ""),
        "step_id": row.get("step_id", ""),
        "applies_to_step_id": row.get("applies_to_step_id", ""),
        "option_group": row.get("option_group", ""),
        "message": row.get("message", ""),
        "payload": payload,
        "review": {
            "decision": row.get("review_decision", ""),
            "reviewer": row.get("reviewer", ""),
            "reviewed_at": row.get("reviewed_at", ""),
            "notes": row.get("review_notes", ""),
        },
        "source": {
            "workbook": row.get("source_workbook", ""),
            "sheet": row.get("source_sheet", ""),
            "cell": row.get("source_cell", ""),
        },
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_review_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


if __name__ == "__main__":
    main()
