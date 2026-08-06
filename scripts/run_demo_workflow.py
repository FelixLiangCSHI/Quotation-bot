from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORMALIZE_SCRIPT = ROOT / "scripts" / "normalize_decision_tree_rules.py"
OUTPUT_SCRIPT = ROOT / "scripts" / "build_demo_outputs.py"
OUTPUT_DIR = ROOT / "Output Sample" / "Generated Demo"


def main() -> None:
    run_step("Normalize Decision Tree rules", [sys.executable, str(NORMALIZE_SCRIPT)])
    run_step("Build customer PDF and audit Excel", [sys.executable, str(OUTPUT_SCRIPT)])

    print("demo_workflow=complete")
    print(f"client_pdf={OUTPUT_DIR / 'client_quote_demo.pdf'}")
    print(f"audit_excel={OUTPUT_DIR / 'internal_audit_demo.xlsx'}")


def run_step(label: str, command: list[str]) -> None:
    print(f"== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()