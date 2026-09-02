"""Headless verification of the demo business flow.

The script never starts a browser or a network call. It exercises the same
functions the demo frontend flow uses so a broken demo is detected before a
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
    QuotationValidationError,
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
    merge_configuration,
    missing_configuration_fields,
    normalize_configuration,
    recalculate_quotation,
)
from app.recommender import QuoteRecommender  # noqa: E402
from app.serialization import to_jsonable  # noqa: E402


OTC_CHEST_TURNS = (
    "I Need a compass OTC fit best chest examination",
    "The customer is ABC Hospital.",
    "Use Singapore.",
    "Use USD.",
    "30%.",
)

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


def run_otc_chest_scenario(recommender: QuoteRecommender) -> None:
    print("Compass OTC chest examination scenario - step by step questions")
    configuration: dict = {}
    turns: list[str] = []
    for index, prompt in enumerate(OTC_CHEST_TURNS):
        turns.append(prompt)
        conversation_text = "\n".join(turns)
        recommendation = to_jsonable(recommender.recommend_from_text(conversation_text))
        configuration = merge_configuration(
            configuration,
            prompt,
            conversation_text,
            recommendation,
        )
        if index == 0:
            _check("System variant", configuration["system_variant"], "DRX Compass OTC")
            _check(
                "Clinical use case",
                configuration["clinical_use_case"],
                "chest_examination",
            )
            _check(
                "Wireless detector quantity",
                _accessory_quantity(configuration, "Wireless Detector"),
                1,
            )
            _check(
                "Wall stand quantity",
                _accessory_quantity(configuration, "Wall Stand"),
                1,
            )
            _check("Grid quantity", _accessory_quantity(configuration, "Grid"), 1)
            _check(
                "Missing fields after the first turn",
                missing_configuration_fields(configuration),
                ["customer name", "region", "currency"],
            )
            try:
                build_quotation_lines(configuration)
            except QuotationValidationError:
                print("  OK  No quotation is generated before the details are known")
            else:
                raise SmokeTestFailure(
                    "A quotation was generated before the commercial details "
                    "were provided."
                )

    totals = recalculate_quotation(build_quotation_lines(configuration))
    _check("Customer", configuration["customer_name"], "ABC Hospital")
    _check("Region", configuration["region"], "Singapore")
    _check("Currency", configuration["currency"], "USD")
    _check("Discount rate", round(totals["discount_rate"], 6), 0.30)
    _check("Approval status", totals["approval_status"], AUTO_APPROVED)
    _check(
        "Quotation product codes",
        [line["product_code"] for line in totals["lines"]],
        ["DRX-COMPASS", "DET-WL-01", "WALL-STD-01", "GRID-01"],
    )
    _check(
        "Main product description",
        totals["lines"][0]["description"],
        "DRX Compass OTC Digital Radiography System",
    )

    excel = generate_quotation_excel(
        "Q-SMOKE-OTC",
        configuration,
        totals,
        totals["approval_status"],
    )
    if not excel:
        raise SmokeTestFailure("OTC chest scenario: quotation Excel is empty.")
    print(f"  OK  Quotation Excel bytes = {len(excel)}")

    pdf = generate_customer_pdf("Q-SMOKE-OTC", configuration, totals)
    if not pdf.startswith(b"%PDF"):
        raise SmokeTestFailure("OTC chest scenario: customer PDF header is missing.")
    print(f"  OK  Customer PDF bytes = {len(pdf)}")


def main() -> int:
    recommender = QuoteRecommender()
    try:
        run_demo_a(recommender)
        run_demo_b(recommender)
        run_per_system_scenario(recommender)
        run_otc_chest_scenario(recommender)
    except SmokeTestFailure as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        return 1
    print("All demo smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
