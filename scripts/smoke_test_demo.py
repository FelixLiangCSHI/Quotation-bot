"""Headless verification of the Streamlit demo business flow.

The script never starts a browser or a network call. It exercises the same
functions the Streamlit page uses so a broken demo is detected before a
presentation.

Usage:
    python scripts/smoke_test_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.quotation import (  # noqa: E402
    AUTO_APPROVED,
    DEMO_A_PROMPT,
    DEMO_B_PROMPT,
    MANAGER_APPROVAL_REQUIRED,
    MANAGER_APPROVED,
    MANAGER_NOT_SUBMITTED,
    build_approval_description,
    build_quotation_lines,
    generate_customer_pdf,
    generate_quotation_excel,
    is_customer_pdf_available,
    normalize_configuration,
    recalculate_quotation,
)
from app.recommender import QuoteRecommender  # noqa: E402
from app.serialization import to_jsonable  # noqa: E402


PER_SYSTEM_PROMPT = (
    "ABC Hospital needs three DRX Compass systems with "
    "one wireless detector per system in USD with a 30% discount."
)


class SmokeTestFailure(AssertionError):
    """Raised when a demo assertion does not hold."""


def _check(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise SmokeTestFailure(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"  OK  {label} = {actual!r}")


def _build(prompt: str, recommender: QuoteRecommender) -> tuple[dict, dict]:
    recommendation = to_jsonable(recommender.recommend_from_text(prompt))
    configuration = normalize_configuration(prompt, recommendation)
    totals = recalculate_quotation(build_quotation_lines(configuration))
    return configuration, totals


def _accessory_quantity(configuration: dict, name: str) -> int:
    for accessory in configuration.get("accessories") or []:
        if accessory["name"] == name:
            return int(accessory["quantity"])
    return 0


def run_demo_a(recommender: QuoteRecommender) -> None:
    print("Demo A - 30% discount, automatic approval")
    configuration, totals = _build(DEMO_A_PROMPT, recommender)

    _check("Customer", configuration["customer_name"], "ABC Hospital")
    _check("Region", configuration["region"], "Singapore")
    _check("Currency", configuration["currency"], "USD")
    _check("Main quantity", configuration["quantity"], 2)
    _check(
        "Detector quantity",
        _accessory_quantity(configuration, "Wireless Detector"),
        2,
    )
    _check("Discount rate", round(totals["discount_rate"], 6), 0.30)
    _check("Approval status", totals["approval_status"], AUTO_APPROVED)

    excel = generate_quotation_excel(
        "Q-SMOKE-A",
        configuration,
        totals,
        totals["approval_status"],
    )
    if not excel:
        raise SmokeTestFailure("Demo A: quotation Excel is empty.")
    print(f"  OK  Quotation Excel bytes = {len(excel)}")

    _check(
        "Customer PDF available",
        is_customer_pdf_available(totals["approval_status"], MANAGER_NOT_SUBMITTED),
        True,
    )
    pdf = generate_customer_pdf("Q-SMOKE-A", configuration, totals)
    if not pdf.startswith(b"%PDF"):
        raise SmokeTestFailure("Demo A: customer PDF header is missing.")
    print(f"  OK  Customer PDF bytes = {len(pdf)}")


def run_demo_b(recommender: QuoteRecommender) -> None:
    print("Demo B - 40% discount, manager approval")
    configuration, totals = _build(DEMO_B_PROMPT, recommender)

    _check("Customer", configuration["customer_name"], "XYZ Medical Centre")
    _check("Region", configuration["region"], "Malaysia")
    _check("Currency", configuration["currency"], "USD")
    _check("Discount rate", round(totals["discount_rate"], 6), 0.40)
    _check("Approval status", totals["approval_status"], MANAGER_APPROVAL_REQUIRED)

    approval_excel = generate_quotation_excel(
        "Q-SMOKE-B",
        configuration,
        totals,
        totals["approval_status"],
        internal_approval=True,
        approval_description=build_approval_description(
            "Q-SMOKE-B",
            configuration,
            totals,
        ),
    )
    if not approval_excel:
        raise SmokeTestFailure("Demo B: approval Excel is empty.")
    print(f"  OK  Internal approval Excel bytes = {len(approval_excel)}")

    _check(
        "Customer PDF before approval",
        is_customer_pdf_available(totals["approval_status"], MANAGER_NOT_SUBMITTED),
        False,
    )
    _check(
        "Customer PDF after manager approval",
        is_customer_pdf_available(totals["approval_status"], MANAGER_APPROVED),
        True,
    )
    pdf = generate_customer_pdf("Q-SMOKE-B", configuration, totals)
    if not pdf.startswith(b"%PDF"):
        raise SmokeTestFailure("Demo B: customer PDF header is missing.")
    print(f"  OK  Customer PDF bytes = {len(pdf)}")


def run_per_system_scenario(recommender: QuoteRecommender) -> None:
    print("Per-system scenario - one wireless detector per system")
    recommendation = to_jsonable(recommender.recommend_from_text(PER_SYSTEM_PROMPT))
    configuration = normalize_configuration(PER_SYSTEM_PROMPT, recommendation)

    _check("Main system quantity", configuration["quantity"], 3)
    _check(
        "Wireless detector quantity",
        _accessory_quantity(configuration, "Wireless Detector"),
        3,
    )


def main() -> int:
    recommender = QuoteRecommender()
    try:
        run_demo_a(recommender)
        run_demo_b(recommender)
        run_per_system_scenario(recommender)
    except SmokeTestFailure as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        return 1
    print("All demo smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
