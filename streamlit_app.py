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
    build_quotation_response,
    can_manager_approve,
    clear_generated_outputs,
    generate_customer_pdf,
    generate_quotation_excel,
    is_customer_pdf_available,
    manager_status_after_quotation_change,
    merge_configuration,
    missing_configuration_fields,
    quotation_export_errors,
    quotation_fingerprint,
    recalculate_quotation,
)
from app.recommender import QuoteRecommender, render_recommendation_text
from app.serialization import to_jsonable


st.set_page_config(
    page_title="AI Quotation Assistant",
    page_icon="QA",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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

    st.title("AI Quotation Assistant")
    st.caption(
        "Offline demonstration using synthetic product and pricing data. "
        "No external AI, SAP, database or email service is connected."
    )

    demo_a, demo_b, reset = st.columns([1, 1, 1])
    with demo_a:
        if st.button(
            "Demo A - Auto Approval",
            width="stretch",
            help="Load the 30% Singapore demonstration.",
        ):
            _load_demo(DEMO_A_PROMPT)
    with demo_b:
        if st.button(
            "Demo B - Manager Approval",
            width="stretch",
            help="Load the 40% Malaysia demonstration.",
        ):
            _load_demo(DEMO_B_PROMPT)
    with reset:
        if st.button("Reset Demo", width="stretch"):
            reset_demo_state()
            st.rerun()

    st.divider()
    conversation_column, quotation_column = st.columns([0.9, 1.35], gap="large")

    with conversation_column:
        _render_conversation()
        _render_configuration()
        prompt = st.chat_input(
            "Describe the customer requirement or reply with a discount",
            key="sales_prompt",
        )
        if prompt:
            with st.spinner("Matching the local configuration catalog..."):
                _process_prompt(prompt)
            st.rerun()
    with quotation_column:
        _render_quotation()

    st.divider()
    st.caption(
        "Demo only — synthetic data and deterministic local matching. "
        "No external AI API, SAP connection, database or email delivery is used."
    )


def _load_demo(prompt: str) -> None:
    reset_demo_state()
    with st.spinner("Preparing the demonstration quotation..."):
        _process_prompt(prompt)
    st.rerun()


def _process_prompt(prompt: str) -> None:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return

    st.session_state["messages"].append({"role": "user", "content": clean_prompt})
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
    st.session_state["configuration"] = configuration
    st.session_state["discount_rate"] = configuration.get("discount_rate")
    invalidate_generated_outputs()

    missing = missing_configuration_fields(configuration)
    if missing:
        catalog_response = render_recommendation_text(recommendation)
        answer = (
            f"{catalog_response}\n\n"
            "To prepare the quotation, please provide: "
            + ", ".join(missing)
            + "."
        )
        _append_assistant_message(answer, recommendation_data)
        return

    if configuration.get("discount_rate") is None:
        answer = (
            f"I have prepared the configuration: "
            f"{configuration['configuration_description']}.\n\n"
            "What discount rate would you like to apply?"
        )
        _append_assistant_message(answer, recommendation_data)
        return

    try:
        lines = build_quotation_lines(configuration)
        totals = recalculate_quotation(lines)
    except QuotationValidationError as exc:
        _append_assistant_message(
            f"I could not prepare the quotation: {exc}",
            recommendation_data,
        )
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

    _append_assistant_message(
        build_quotation_response(configuration, totals),
        recommendation_data,
    )


def _append_assistant_message(
    content: str,
    recommendation: dict[str, Any] | None = None,
) -> None:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if recommendation:
        message["recommendation"] = recommendation
    st.session_state["messages"].append(message)


def _render_conversation() -> None:
    st.subheader("Sales conversation")
    with st.container(height=690, border=True):
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])


def _render_configuration() -> None:
    with st.container(border=True):
        st.subheader("Configuration Summary")
        configuration = st.session_state["configuration"]
        if not configuration:
            st.info("Start the conversation or load a demo to create a configuration.")
            return

        customer, region, currency = st.columns(3)
        customer.markdown(
            f"**Customer**  \n{configuration.get('customer_name') or 'Not provided'}"
        )
        region.markdown(f"**Region**  \n{configuration.get('region') or 'Not provided'}")
        currency.markdown(
            f"**Currency**  \n{configuration.get('currency') or 'Not provided'}"
        )

        product, quantity = st.columns([3, 1])
        product.markdown(
            f"**Main Product**  \n{configuration.get('main_product') or 'Not provided'}"
        )
        quantity.markdown(f"**Quantity**  \n{configuration.get('quantity') or 1}")

        accessory_text = " · ".join(
            f"{item['quantity']} × {item['name']}"
            for item in configuration.get("accessories") or []
        )
        st.markdown(f"**Accessories**  \n{accessory_text or 'Not provided'}")
        st.caption(
            "Configuration: "
            + (configuration.get("configuration_description") or "Not provided")
        )


def _render_quotation() -> None:
    with st.container(border=True):
        st.subheader("Quotation Table")
        if not st.session_state["quotation_lines"]:
            st.info("Complete the configuration and discount in the conversation.")
            return
        _render_quotation_editor()

    totals = st.session_state["quotation_totals"]
    with st.container(border=True):
        st.subheader("Discount Approval")
        _render_totals_and_approval(totals)

    with st.container(border=True):
        st.subheader("Output Actions")
        _render_output_actions(totals)


def _render_quotation_editor() -> None:
    current_lines = st.session_state["quotation_lines"]
    st.caption(
        "You can adjust Quantity and Quotation Unit Price. "
        "Approval status updates automatically."
    )
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
                "List Unit Price",
                min_value=0.01,
                format="%.2f",
            ),
            "Quotation Unit Price": st.column_config.NumberColumn(
                "Quotation Unit Price",
                min_value=0.0,
                step=100.0,
                format="%.2f",
                required=True,
            ),
            "List Total": st.column_config.NumberColumn("List Total", format="%.2f"),
            "Quotation Total": st.column_config.NumberColumn(
                "Quotation Total",
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
    list_total, quotation_total, discount = st.columns(3)
    list_total.metric("List Total", f"{currency} {totals['list_total']:,.2f}")
    quotation_total.metric(
        "Quotation Total",
        f"{currency} {totals['quotation_total']:,.2f}",
    )
    discount.metric("Discount Rate", f"{totals['discount_rate']:.1%}")

    threshold, status = st.columns([1, 2])
    threshold.metric("Approval Threshold", f"{DISCOUNT_APPROVAL_THRESHOLD:.1%}")

    approval_status = totals["approval_status"]
    if approval_status == AUTO_APPROVED:
        status.success(
            "**Automatically approved**  \n"
            "Discount rate is within the 35% Sales authority."
        )
    elif approval_status == MANAGER_APPROVAL_REQUIRED:
        status.warning(
            "**Manager approval required**  \n"
            "Discount rate exceeds the 35% Sales authority."
        )
        _render_manager_status()
    else:
        status.error("**Quotation needs correction before approval.**")


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
