from __future__ import annotations

from datetime import date
from typing import Any, Callable

import streamlit as st

from app.quotation import (
    AUTO_APPROVED,
    DEMO_A_PROMPT,
    DEMO_B_PROMPT,
    DISCOUNT_APPROVAL_THRESHOLD,
    MANAGER_APPROVAL_REQUIRED,
    MANAGER_APPROVED,
    MANAGER_NOT_SUBMITTED,
    MANAGER_PENDING,
    MANAGER_REJECTED,
    MANAGER_REVISION_REQUESTED,
    WELCOME_MESSAGE,
    APPROVAL_FINGERPRINT_MISMATCH_MESSAGE,
    QuotationValidationError,
    build_approval_description,
    build_quotation_lines,
    can_manager_approve,
    clear_generated_outputs,
    clinical_use_case_label,
    generate_customer_pdf,
    generate_quotation_excel,
    is_customer_pdf_available,
    is_supported_main_product,
    manager_status_after_quotation_change,
    merge_configuration,
    missing_configuration_fields,
    quotation_export_errors,
    quotation_fingerprint,
    recalculate_quotation,
)
from app.recommender import QuoteRecommender
from app.serialization import to_jsonable


st.set_page_config(
    page_title="AI Quotation Assistant",
    page_icon="QA",
    layout="wide",
    initial_sidebar_state="expanded",
)


# The scripted demo prompts stay available for tests and for the hidden
# presentation fallback, but they are no longer shown on the main page.
DEMO_PROMPTS = (DEMO_A_PROMPT, DEMO_B_PROMPT)

HEADER_SUBTITLE = (
    "Describe the customer requirement. I will prepare the configuration, "
    "calculate the discount and route the quotation for approval when needed."
)
HEADER_NOTE = "Offline demonstration using synthetic product and pricing data."

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

COMPACT_STYLE = """
<style>
[data-testid="stAppViewBlockContainer"] {
    padding-top: 2.2rem;
    padding-bottom: 2.5rem;
    max-width: 1180px;
}
</style>
"""


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


@st.cache_resource
def get_recommender() -> QuoteRecommender:
    return QuoteRecommender()


def initialize_demo_state() -> None:
    defaults: dict[str, Any] = {
        "messages": [{"role": "assistant", "content": WELCOME_MESSAGE}],
        "requirements": {"turns": []},
        "configuration": {},
        "quotation_lines": [],
        "quotation_totals": {},
        "quotation_id": "",
        "discount_rate": None,
        "approval_status": "",
        "manager_approval_status": MANAGER_NOT_SUBMITTED,
        "generated_files": {},
        "editor_version": 0,
        "submitted_quotation_fingerprint": None,
        "quick_replies": {"field": None, "options": []},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo_state() -> None:
    for key in list(st.session_state):
        if key.startswith("quotation_editor_") or key in {
            "messages",
            "requirements",
            "configuration",
            "quotation_lines",
            "quotation_totals",
            "quotation_id",
            "discount_rate",
            "approval_status",
            "manager_approval_status",
            "generated_files",
            "editor_version",
            "submitted_quotation_fingerprint",
            "quick_replies",
            "sales_prompt",
        }:
            del st.session_state[key]
    initialize_demo_state()


def invalidate_generated_outputs() -> None:
    """Drop cached exports and the manager submission after any quotation edit."""
    clear_generated_outputs(st.session_state["generated_files"])
    st.session_state["submitted_quotation_fingerprint"] = None


def main() -> None:
    initialize_demo_state()
    st.markdown(COMPACT_STYLE, unsafe_allow_html=True)
    _render_sidebar()

    st.title("AI Quotation Assistant")
    st.caption(HEADER_SUBTITLE)
    st.caption(HEADER_NOTE)

    _render_conversation()

    prompt = st.chat_input(
        "Describe the customer requirement or reply with a discount",
        key="sales_prompt",
    )
    if prompt:
        with st.spinner("Matching the local configuration catalog..."):
            _process_prompt(prompt)
        st.rerun()

    _render_quick_replies()
    _render_configuration()
    _render_quotation()

    st.divider()
    st.caption(
        "Demo only — synthetic data and deterministic local matching. "
        "No external AI API, SAP connection, database or email delivery is used."
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### AI Quotation")
        st.caption("Sales workspace")
        if st.button("New quotation", type="primary", width="stretch"):
            reset_demo_state()
            st.rerun()

        st.divider()
        st.markdown("**Workflow progress**")
        current_stage = workflow_stage(
            {
                "configuration": st.session_state["configuration"],
                "quotation_lines": st.session_state["quotation_lines"],
                "approval_status": st.session_state["approval_status"],
                "manager_approval_status": st.session_state[
                    "manager_approval_status"
                ],
            }
        )
        current_index = WORKFLOW_STAGES.index(current_stage)
        for index, stage in enumerate(WORKFLOW_STAGES):
            if index < current_index:
                marker = "✓"
            elif index == current_index:
                marker = "▶"
            else:
                marker = "·"
            st.markdown(f"{marker} {index + 1}. {stage}")
        if current_stage == "Approval":
            st.caption("Approval complete")

        st.divider()
        st.markdown("**Current draft**")
        for label, value in _current_draft_rows():
            st.caption(f"{label}: {value}")

        with st.expander("Example requests"):
            for title, example_prompt in EXAMPLE_REQUESTS:
                if st.button(title, key=f"example_{title}", width="stretch"):
                    _load_demo(example_prompt)

        with st.expander("System scope"):
            st.markdown(
                "**Supported products**\n\n"
                "- DRX Compass\n"
                "- DRX Revolution\n"
                "- DRX Rise\n\n"
                "**Approval rule**\n\n"
                "- Discount ≤ 35%: automatic\n"
                "- Discount > 35%: manager review\n\n"
                "Synthetic offline demonstration. "
                "No AI API, SAP, database or email service is connected."
            )


def _current_draft_rows() -> list[tuple[str, str]]:
    configuration = st.session_state["configuration"] or {}
    placeholder = "—"
    accessories = configuration.get("accessories") or []
    discount_rate = st.session_state.get("discount_rate")
    approval_status = st.session_state.get("approval_status")
    manager_status = st.session_state.get("manager_approval_status")

    if approval_status == AUTO_APPROVED:
        approval_text = "Automatically approved"
    elif approval_status == MANAGER_APPROVAL_REQUIRED:
        approval_text = f"Manager review ({manager_status.replace('_', ' ').title()})"
    else:
        approval_text = placeholder

    main_product = configuration.get("main_product") or placeholder
    if main_product != placeholder and accessories:
        main_product = f"{main_product} + {len(accessories)} accessory lines"

    return [
        ("Customer", configuration.get("customer_name") or placeholder),
        ("Main product", main_product),
        ("Quantity", str(configuration.get("quantity") or placeholder)),
        ("Region", configuration.get("region") or placeholder),
        ("Currency", configuration.get("currency") or placeholder),
        (
            "Discount",
            f"{discount_rate:.1%}" if isinstance(discount_rate, (int, float))
            else placeholder,
        ),
        ("Approval status", approval_text),
    ]


def _render_quick_replies() -> None:
    quick_replies = st.session_state.get("quick_replies") or {}
    options = quick_replies.get("options") or []
    field = quick_replies.get("field")
    if not options or not field:
        return

    st.caption("Quick replies")
    columns = st.columns(len(options))
    for column, option in zip(columns, options):
        if column.button(option, key=f"quick_{field}_{option}", width="stretch"):
            with st.spinner("Updating the configuration..."):
                _process_prompt(quick_reply_prompt(field, option))
            st.rerun()


def _load_demo(prompt: str) -> None:
    reset_demo_state()
    with st.spinner("Preparing the quotation..."):
        _process_prompt(prompt)
    st.rerun()


def _process_prompt(prompt: str) -> None:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return

    st.session_state["messages"].append({"role": "user", "content": clean_prompt})

    if is_low_information_prompt(clean_prompt):
        _set_quick_replies(None, ())
        _append_assistant_message(LOW_INFORMATION_REPLY)
        return

    turns = st.session_state["requirements"]["turns"]
    turns.append(clean_prompt)
    conversation_text = "\n".join(turns)

    recommendation = get_recommender().recommend_from_text(conversation_text)
    recommendation_data = to_jsonable(recommendation)
    configuration = merge_configuration(
        st.session_state["configuration"],
        clean_prompt,
        conversation_text,
        recommendation_data,
    )
    configuration, product_blocked = guard_unsupported_product(configuration)
    st.session_state["configuration"] = configuration
    st.session_state["discount_rate"] = configuration.get("discount_rate")
    invalidate_generated_outputs()

    plan = plan_next_reply(configuration, product_blocked)
    if not plan["ready"]:
        _set_quick_replies(plan["field"], plan["quick_replies"])
        _append_assistant_message(plan["reply"])
        return

    try:
        lines = build_quotation_lines(configuration)
        totals = recalculate_quotation(lines)
    except QuotationValidationError as exc:
        _set_quick_replies(None, ())
        _append_assistant_message(f"I could not prepare the quotation: {exc}")
        return

    st.session_state["quotation_lines"] = totals["lines"]
    st.session_state["quotation_totals"] = totals
    st.session_state["discount_rate"] = totals["discount_rate"]
    st.session_state["approval_status"] = totals["approval_status"]
    st.session_state["manager_approval_status"] = MANAGER_NOT_SUBMITTED
    invalidate_generated_outputs()
    st.session_state["editor_version"] += 1
    if not st.session_state["quotation_id"]:
        st.session_state["quotation_id"] = f"Q-{date.today():%Y%m%d}-001"

    _set_quick_replies(None, ())
    _append_assistant_message(
        build_conversation_summary(configuration, totals),
        recommendation_data,
    )


def _set_quick_replies(field: str | None, options: Any) -> None:
    st.session_state["quick_replies"] = {
        "field": field,
        "options": list(options or []),
    }


def _append_assistant_message(
    content: str,
    recommendation: dict[str, Any] | None = None,
) -> None:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if recommendation:
        message["recommendation"] = recommendation
    st.session_state["messages"].append(message)


def _render_conversation() -> None:
    with st.container(height=520, border=True):
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])


def _render_configuration() -> None:
    configuration = st.session_state["configuration"]
    if not configuration:
        return

    with st.container(border=True):
        st.markdown("**Configuration summary**")
        customer, region, currency, quantity = st.columns(4)
        customer.markdown(
            f"**Customer**  \n{configuration.get('customer_name') or '—'}"
        )
        region.markdown(f"**Region**  \n{configuration.get('region') or '—'}")
        currency.markdown(f"**Currency**  \n{configuration.get('currency') or '—'}")
        quantity.markdown(f"**Quantity**  \n{configuration.get('quantity') or 1}")

        st.markdown(f"**Main product**  \n{configuration.get('main_product') or '—'}")
        variant, clinical = st.columns(2)
        variant.markdown(
            f"**System variant**  \n{configuration.get('system_variant') or '—'}"
        )
        clinical.markdown(
            "**Clinical use**  \n"
            + (clinical_use_case_label(configuration.get("clinical_use_case")) or "—")
        )
        accessory_text = " · ".join(
            f"{item['quantity']} × {item['name']}"
            for item in configuration.get("accessories") or []
        )
        st.markdown(f"**Accessories**  \n{accessory_text or '—'}")

        with st.expander("View configuration details"):
            st.write(configuration.get("configuration_description") or "—")


def _render_quotation() -> None:
    if not st.session_state["quotation_lines"]:
        return

    st.subheader("Quotation Preview")
    st.caption(
        "Review the generated quotation below. "
        "Quantity and quotation price remain editable."
    )
    _render_quotation_editor()

    totals = st.session_state["quotation_totals"]
    _render_totals_and_approval(totals)

    with st.container(border=True):
        st.markdown("**Output actions**")
        _render_output_actions(totals)


def _render_quotation_editor() -> None:
    current_lines = st.session_state["quotation_lines"]
    display_rows = [
        {
            "Product Code": line["product_code"],
            "Description": line["description"],
            "Quantity": line["quantity"],
            "List Unit Price": line["list_unit_price"],
            "Quotation Unit Price": line["quotation_unit_price"],
            "List Total": line["list_line_total"],
            "Quotation Total": line["quotation_line_total"],
        }
        for line in current_lines
    ]

    edited_rows = st.data_editor(
        display_rows,
        key=f"quotation_editor_{st.session_state['editor_version']}",
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        disabled=[
            "Product Code",
            "Description",
            "List Unit Price",
            "List Total",
            "Quotation Total",
        ],
        column_config={
            "Quantity": st.column_config.NumberColumn(
                "Quantity",
                min_value=1,
                step=1,
                format="%d",
                required=True,
            ),
            "List Unit Price": st.column_config.NumberColumn(
                "List Price",
                min_value=0.01,
                format="%.2f",
            ),
            "Quotation Unit Price": st.column_config.NumberColumn(
                "Quote Price",
                min_value=0.0,
                step=100.0,
                format="%.2f",
                required=True,
            ),
            "List Total": st.column_config.NumberColumn("List Total", format="%.2f"),
            "Quotation Total": st.column_config.NumberColumn(
                "Quote Total",
                format="%.2f",
            ),
        },
    )

    edited_lines = [
        {
            "product_code": row["Product Code"],
            "description": row["Description"],
            "quantity": row["Quantity"],
            "list_unit_price": row["List Unit Price"],
            "quotation_unit_price": row["Quotation Unit Price"],
        }
        for row in edited_rows
    ]
    recalculated = recalculate_quotation(edited_lines)

    if quotation_fingerprint(current_lines) != quotation_fingerprint(recalculated["lines"]):
        st.session_state["manager_approval_status"] = (
            manager_status_after_quotation_change(
                current_lines,
                recalculated["lines"],
                st.session_state["manager_approval_status"],
            )
        )
        st.session_state["quotation_lines"] = recalculated["lines"]
        st.session_state["quotation_totals"] = recalculated
        st.session_state["discount_rate"] = recalculated["discount_rate"]
        st.session_state["approval_status"] = recalculated["approval_status"]
        invalidate_generated_outputs()
        st.rerun()

    st.session_state["quotation_totals"] = recalculated
    st.session_state["discount_rate"] = recalculated["discount_rate"]
    st.session_state["approval_status"] = recalculated["approval_status"]

    for warning in recalculated["warnings"]:
        st.warning(warning)
    for error in recalculated["errors"]:
        st.error(error)


def _render_totals_and_approval(totals: dict[str, Any]) -> None:
    currency = st.session_state["configuration"].get("currency") or ""
    list_total, quotation_total, discount, threshold = st.columns(4)
    list_total.metric("List Total", f"{currency} {totals['list_total']:,.2f}")
    quotation_total.metric(
        "Quotation Total",
        f"{currency} {totals['quotation_total']:,.2f}",
    )
    discount.metric("Discount Rate", f"{totals['discount_rate']:.1%}")
    threshold.metric("Approval Threshold", f"{DISCOUNT_APPROVAL_THRESHOLD:.1%}")

    approval_status = totals["approval_status"]
    if approval_status == AUTO_APPROVED:
        st.success(
            "**Automatically approved**  \n"
            "Discount rate is within the 35% Sales authority."
        )
    elif approval_status == MANAGER_APPROVAL_REQUIRED:
        st.warning(
            "**Manager approval required**  \n"
            "Discount rate exceeds the 35% Sales authority."
        )
        _render_manager_status()
    else:
        st.error("**Quotation needs correction before approval.**")


def _render_manager_status() -> None:
    manager_status = st.session_state["manager_approval_status"]
    if manager_status == MANAGER_NOT_SUBMITTED:
        st.caption("Approval request has not been submitted.")
    elif manager_status == MANAGER_PENDING:
        st.info(
            "Approval request submitted  \n"
            "Approver: Sales Director  \nStatus: Pending approval"
        )
    elif manager_status == MANAGER_APPROVED:
        st.success(
            "**Approved by Sales Director**  \nCustomer PDF is now available."
        )
    elif manager_status == MANAGER_REVISION_REQUESTED:
        st.warning("Revision requested by Sales Director")
    elif manager_status == MANAGER_REJECTED:
        st.error("Quotation rejected by Sales Director")


def _render_output_actions(totals: dict[str, Any]) -> None:
    configuration = st.session_state["configuration"]
    export_errors = quotation_export_errors(configuration, totals)
    if export_errors:
        st.error(
            "This quotation cannot be exported yet:\n\n"
            + "\n".join(f"- {error}" for error in export_errors)
        )
        return

    quotation_id = st.session_state["quotation_id"]
    approval_status = totals["approval_status"]
    manager_status = st.session_state["manager_approval_status"]

    if approval_status == AUTO_APPROVED:
        excel_data = _generated_file(
            "quotation_excel",
            lambda: generate_quotation_excel(
                quotation_id,
                configuration,
                totals,
                approval_status,
            ),
        )
        if excel_data:
            st.download_button(
                "Download Quotation Excel",
                data=excel_data,
                file_name=f"Quotation_{quotation_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
    else:
        approval_description = build_approval_description(
            quotation_id,
            configuration,
            totals,
        )
        approval_excel = _generated_file(
            "approval_excel",
            lambda: generate_quotation_excel(
                quotation_id,
                configuration,
                totals,
                approval_status,
                internal_approval=True,
                approval_description=approval_description,
            ),
        )
        if approval_excel:
            st.download_button(
                "Download Internal Approval Excel",
                data=approval_excel,
                file_name=f"Approval_Request_{quotation_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )

        with st.popover("Copy Approval Description", width="stretch"):
            st.code(approval_description, language=None)
            st.caption("Use the copy icon in the code block.")

        if st.button(
            "Send for Approval — Demo",
            width="stretch",
            disabled=manager_status == MANAGER_PENDING,
        ):
            st.session_state["manager_approval_status"] = MANAGER_PENDING
            st.session_state["submitted_quotation_fingerprint"] = (
                quotation_fingerprint(st.session_state["quotation_lines"])
            )
            st.rerun()

        with st.expander("Manager Demo Controls"):
            st.caption("These controls simulate the Sales Director response.")
            approve, revision, reject = st.columns(3)
            controls_disabled = (
                st.session_state["manager_approval_status"] != MANAGER_PENDING
            )
            if approve.button(
                "Approve",
                width="stretch",
                disabled=controls_disabled,
            ):
                # The approval must still belong to the submitted quotation.
                if can_manager_approve(
                    st.session_state["quotation_lines"],
                    st.session_state["submitted_quotation_fingerprint"],
                ):
                    st.session_state["manager_approval_status"] = MANAGER_APPROVED
                    st.session_state["generated_files"].pop("customer_pdf", None)
                    st.rerun()
                else:
                    st.session_state["manager_approval_status"] = MANAGER_NOT_SUBMITTED
                    st.session_state["submitted_quotation_fingerprint"] = None
                    st.error(APPROVAL_FINGERPRINT_MISMATCH_MESSAGE)
            if revision.button(
                "Request Revision",
                width="stretch",
                disabled=controls_disabled,
            ):
                st.session_state["manager_approval_status"] = (
                    MANAGER_REVISION_REQUESTED
                )
                st.rerun()
            if reject.button(
                "Reject",
                width="stretch",
                disabled=controls_disabled,
            ):
                st.session_state["manager_approval_status"] = MANAGER_REJECTED
                st.rerun()

    pdf_available = is_customer_pdf_available(approval_status, manager_status)
    if pdf_available:
        pdf_data = _generated_file(
            "customer_pdf",
            lambda: generate_customer_pdf(
                quotation_id,
                configuration,
                totals,
            ),
        )
        if pdf_data:
            st.download_button(
                "Download Customer Quotation PDF",
                data=pdf_data,
                file_name=f"Quotation_{quotation_id}.pdf",
                mime="application/pdf",
                width="stretch",
            )
    else:
        st.button(
            "Download Customer Quotation PDF",
            disabled=True,
            width="stretch",
        )
        st.caption("The customer PDF will be available after manager approval.")


def _generated_file(name: str, builder: Callable[[], bytes]) -> bytes | None:
    generated_files = st.session_state["generated_files"]
    if name in generated_files:
        return generated_files[name]
    try:
        generated_files[name] = builder()
    except (ImportError, OSError, TypeError, ValueError) as exc:
        st.error(f"Could not generate the requested file: {exc}")
        return None
    return generated_files[name]


if __name__ == "__main__":
    main()
