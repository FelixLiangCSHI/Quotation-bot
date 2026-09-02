"""Conversation-flow logic for the quotation assistant.

Pure business logic extracted from the retired Streamlit UI so any frontend
(web app, API client, chatbot platform) can drive the same conversation:
one question at a time, quick replies, unsupported-product guarding, and
workflow stage tracking. This module has no UI framework dependency.
"""

from __future__ import annotations

from typing import Any

from app.quotation import (
    AUTO_APPROVED,
    DEMO_A_PROMPT,
    DEMO_B_PROMPT,
    DISCOUNT_APPROVAL_THRESHOLD,
    MANAGER_APPROVED,
    clinical_use_case_label,
    is_supported_main_product,
    missing_configuration_fields,
)


# The scripted demo prompts stay available for tests and demo fallbacks.
DEMO_PROMPTS = (DEMO_A_PROMPT, DEMO_B_PROMPT)

LOW_INFORMATION_PROMPTS = frozenset(
    {
        "hi",
        "hey",
        "hello",
        "test",
        "testing",
        "start",
        "let me try",
        "let us try",
        "i want to try",
        "i would like to try",
        "can i try",
        "try",
        "try it",
        "ok",
        "okay",
    }
)

LOW_INFORMATION_REPLY = (
    "Of course. Tell me the customer name and the imaging system they need.\n\n"
    "You can provide the full request in one message or add the details "
    "step by step."
)

MISSING_FIELD_ORDER = (
    "customer_name",
    "region",
    "currency",
    "main_product",
)

FIELD_LABELS = {
    "customer_name": "customer name",
    "region": "region",
    "currency": "currency",
    "main_product": "main product",
}

FIELD_QUESTIONS = {
    "customer_name": "Which customer is this quotation for?",
    "region": "Which sales region should I use?",
    "currency": "Which currency should the quotation use?",
    "main_product": (
        "Which system should I configure: "
        "DRX Compass, DRX Revolution or DRX Rise?"
    ),
    "discount_rate": "What discount rate would you like to apply?",
}

MAIN_PRODUCT_OPTIONS = ("DRX Compass", "DRX Revolution", "DRX Rise")

QUICK_REPLY_OPTIONS = {
    "region": (
        "Singapore",
        "Malaysia",
        "United States",
        "Canada",
        "China",
        "Europe",
    ),
    "currency": ("USD", "SGD", "MYR", "CAD", "EUR", "CNY"),
    "main_product": MAIN_PRODUCT_OPTIONS,
    "discount_rate": ("25%", "30%", "35%", "40%"),
}

UNSUPPORTED_PRODUCT_MESSAGE = (
    "I could not match that request to a supported quotation model.\n\n"
    "This demonstration currently supports:\n"
    "- DRX Compass\n"
    "- DRX Revolution\n"
    "- DRX Rise\n\n"
    "Which system should I use?"
)

EXAMPLE_REQUESTS = (
    (
        "Hospital room upgrade",
        "ABC Hospital in Singapore needs two DRX Compass systems, "
        "two wireless detectors and a three-year warranty. "
        "Prepare the quotation in USD with a 30% discount.",
    ),
    (
        "Mobile imaging requirement",
        "North Medical Centre in Canada needs one DRX Revolution system "
        "with one wireless detector. "
        "Prepare the quotation in CAD with a 28% discount.",
    ),
    (
        "Multi-system rollout",
        "Regional Hospital in Malaysia needs three DRX Compass systems "
        "with one wireless detector per system and a three-year warranty. "
        "Prepare the quotation in USD with a 38% discount.",
    ),
)

WORKFLOW_STAGES = ("Requirements", "Configuration", "Quotation", "Approval")

def is_low_information_prompt(text: str) -> bool:
    """Return True for greetings and 'let me try' style openings."""
    normalized = " ".join(str(text or "").lower().split())
    normalized = normalized.strip(" .!?,'\"")
    if not normalized:
        return True
    return normalized in LOW_INFORMATION_PROMPTS


def next_missing_field(configuration: dict[str, Any]) -> str | None:
    """Return the single next field the assistant should ask about."""
    missing = set(missing_configuration_fields(configuration or {}))
    for field in MISSING_FIELD_ORDER:
        if FIELD_LABELS[field] in missing:
            return field
    if (configuration or {}).get("discount_rate") is None:
        return "discount_rate"
    return None


def next_missing_question(configuration: dict[str, Any]) -> str | None:
    """Return one question at a time for the first missing field."""
    field = next_missing_field(configuration)
    if field is None:
        return None
    return FIELD_QUESTIONS[field]


def quick_replies_for_field(field: str | None) -> tuple[str, ...]:
    if not field:
        return ()
    return tuple(QUICK_REPLY_OPTIONS.get(field, ()))


def quick_reply_prompt(field: str, option: str) -> str:
    """Turn a quick reply into natural language so the parser stays in charge."""
    if field == "discount_rate":
        return f"Apply a {option} discount."
    return f"Use {option}."


def guard_unsupported_product(
    configuration: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Drop a main product that is not in the supported price book."""
    configuration = dict(configuration or {})
    main_product = str(configuration.get("main_product") or "")
    if main_product and not is_supported_main_product(main_product):
        configuration["main_product"] = ""
        configuration["system_variant"] = ""
        configuration["configuration_description"] = ""
        return configuration, True
    return configuration, False


def describe_known_configuration(configuration: dict[str, Any]) -> str:
    """Short recap of what has been captured so far."""
    configuration = configuration or {}
    parts = []
    if configuration.get("customer_name"):
        parts.append(f"Customer: {configuration['customer_name']}")
    if configuration.get("region"):
        parts.append(f"Region: {configuration['region']}")
    if configuration.get("currency"):
        parts.append(f"Currency: {configuration['currency']}")
    if configuration.get("main_product"):
        quantity = configuration.get("quantity") or 1
        parts.append(f"System: {quantity} × {configuration['main_product']}")
    if configuration.get("system_variant"):
        parts.append(f"System variant: {configuration['system_variant']}")
    clinical_label = clinical_use_case_label(configuration.get("clinical_use_case"))
    if clinical_label:
        parts.append(f"Clinical use: {clinical_label}")
    for accessory in configuration.get("accessories") or []:
        parts.append(f"{accessory['quantity']} × {accessory['name']}")
    if not parts:
        return ""
    return "Noted so far:\n" + "\n".join(f"- {part}" for part in parts)


def plan_next_reply(
    configuration: dict[str, Any],
    product_blocked: bool = False,
) -> dict[str, Any]:
    """Pure conversation planner: one question, optional quick replies."""
    field = next_missing_field(configuration)
    if field is None:
        return {"reply": "", "field": None, "quick_replies": (), "ready": True}

    if product_blocked and field == "main_product":
        return {
            "reply": UNSUPPORTED_PRODUCT_MESSAGE,
            "field": "main_product",
            "quick_replies": MAIN_PRODUCT_OPTIONS,
            "ready": False,
        }

    recap = describe_known_configuration(configuration)
    question = FIELD_QUESTIONS[field]
    reply = f"{recap}\n\n{question}" if recap else question
    return {
        "reply": reply,
        "field": field,
        "quick_replies": quick_replies_for_field(field),
        "ready": False,
    }


def build_conversation_summary(
    configuration: dict[str, Any],
    totals: dict[str, Any],
) -> str:
    """Concise chat wording for a completed quotation."""
    customer = configuration.get("customer_name") or "the customer"
    system_name = configuration.get("system_variant") or configuration["main_product"]
    lines = [f"{configuration.get('quantity') or 1} × {system_name}"]
    clinical_label = clinical_use_case_label(configuration.get("clinical_use_case"))
    if clinical_label:
        lines[0] += f" configured for {clinical_label.casefold()}"
    lines.extend(
        f"{accessory['quantity']} × {accessory['name']}"
        for accessory in configuration.get("accessories") or []
    )
    body = "\n".join(lines)
    discount = f"{totals['discount_rate']:.0%}"
    if totals["approval_status"] == AUTO_APPROVED:
        closing = (
            "The quotation is ready below.\n"
            f"The current discount is {discount}, so it is within Sales authority."
        )
    else:
        closing = (
            "The quotation is ready below.\n\n"
            f"The current discount is {discount}, which exceeds the "
            f"{DISCOUNT_APPROVAL_THRESHOLD:.0%} Sales authority.\n"
            "Manager approval is required before the customer PDF is released."
        )
    return (
        f"I have prepared the configuration for {customer}:\n\n"
        f"{body}\n\n{closing}"
    )


def workflow_stage(state: dict[str, Any]) -> str:
    """Derive the current workflow stage from the existing session state."""
    configuration = state.get("configuration") or {}
    quotation_lines = state.get("quotation_lines") or []
    if not configuration:
        return "Requirements"
    if quotation_lines:
        approved = state.get("approval_status") == AUTO_APPROVED or (
            state.get("manager_approval_status") == MANAGER_APPROVED
        )
        return "Approval" if approved else "Quotation"
    return "Configuration"
