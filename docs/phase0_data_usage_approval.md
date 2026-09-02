# Phase 0 / Subphase 03 - Data Usage Boundary for Azure OpenAI

Date: 2026-09-02
Status: Approval request prepared - awaiting IT / security / data owner confirmation
Source references: `docs/quotation_bot_mvp_vs_production_architecture.md` (Phase 0 item 3), `docs/phase0_pilot_scope.md` (sign-off item 5), `docs/phase0_azure_openai_access_request.md` (Section 3).

## 1. Purpose

Confirm whether quotation, product, and rule data may be sent to Azure OpenAI, and define exactly **which data categories cross the LLM boundary** during the Beta pilot. Nothing is sent to any LLM until this approval is granted.

## 2. Data Inventory in This Repository

| Data asset | Content | Volume | Current sensitivity note |
|---|---|---|---|
| `quotation_snapshot.json` - products | Product IDs, system family (FMT/OTC), category, short descriptions, source comments | 380 products | Contains internal catalog wording and workbook author comments; one comment includes an internal cost figure |
| `quotation_snapshot.json` - matrices | Compatibility (590), detector/grid (33), generator/tube (69) relationships | 692 rows | Internal engineering compatibility data |
| `quotation_snapshot.json` - rule signals | 984 extracted rule signals incl. 206 free-text constraints | 984 | Free text may embed internal business reasoning |
| `rules/merged_rules.json` | 700 confirmed executable rules | 700 | Structured, derived from the above |
| Demo pricing in `app/quotation.py` | List unit prices used by the Streamlit demo | ~10 items | **Synthetic demo data** per README ("Product, pricing and customer data in this repository is synthetic demo data") |
| User chat input | Sales quote questions typed during the pilot | Ad hoc | May mention customer names, regions, deal context |

## 3. Proposed LLM Data Boundary (what is / is not sent)

### 3.1 Sent to Azure OpenAI (requires approval)

| Category | Why needed | Minimization applied |
|---|---|---|
| User question text | Intent and field extraction | Sent as-is; users instructed not to paste customer PII |
| Extracted field names/values (system family, region, detector type, etc.) | Explanation wording | Only fields relevant to the current turn |
| Rule-engine verdict + triggered rule messages | Natural-language explanation | Only the rules fired for this request, not the full rule set |

### 3.2 NOT sent to Azure OpenAI (kept local)

| Category | Handling |
|---|---|
| Full `quotation_snapshot.json` / `rules/merged_rules.json` | Loaded only by the local rule engine; never placed in prompts |
| Pricing, cost, and discount data | Stays in local quotation calculation; excluded from prompts |
| Workbook author comments (incl. internal cost notes) | Excluded from prompts |
| Customer names / PII | Out of pilot scope; users instructed not to enter it |
| Chat history retention | No long-term storage; session memory only (per Phase 5 decision) |

### 3.3 Boundary principle

> The LLM receives only the minimum text needed for the current turn: the user question, the extracted fields, and the fired rule messages. The rule engine, data files, and pricing never cross the boundary.

## 4. Questions for IT / Security / Data Owner

| # | Question | Decision needed |
|---:|---|---|
| 1 | May user quote questions (free text) be sent to the approved Azure OpenAI resource? | Yes / No / With conditions |
| 2 | May extracted configuration fields (product IDs, regions, detector types) be sent? | Yes / No / With conditions |
| 3 | May fired rule messages (short constraint text) be sent for explanation wording? | Yes / No / With conditions |
| 4 | Is the Azure OpenAI resource covered by a no-training / no-retention data agreement? | Confirm |
| 5 | Are there data residency / region requirements for prompts? | Confirm |
| 6 | Is prompt/response logging required or prohibited for the pilot? | Confirm |

## 5. Assumed Safeguards (pilot commitments)

1. Azure OpenAI is used within the company tenant; prompts are not used for model training (per standard Azure OpenAI data handling - to be confirmed by IT in question 4).
2. All data files remain local; only per-turn minimal context enters prompts.
3. No secrets, credentials, pricing, or customer PII in prompts.
4. If any question in Section 4 is answered "No", the affected category is removed from prompts and the pilot proceeds with reduced LLM scope (e.g. template-based explanations).

## 6. Deliverable Status

| Deliverable | Status |
|---|---|
| Data inventory and classification (this document) | Done |
| Proposed LLM data boundary | Done |
| Sign-off from IT / security / data owner | Pending |
| Boundary enforced in code (prompt construction) | Deferred to Phase 2 implementation |
