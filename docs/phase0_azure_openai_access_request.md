# Phase 0 / Subphase 02 - Azure OpenAI Endpoint and Model Access

Date: 2026-09-02
Status: Access request prepared - awaiting IT / AI platform confirmation
Source references: `docs/quotation_bot_mvp_vs_production_architecture.md` (Phase 0 item 2, Phase 2), `docs/phase0_pilot_scope.md` (sign-off item 4).

## 1. Purpose

Confirm the Azure OpenAI endpoint and model access needed for the Beta pilot. The LLM is used **only** for intent extraction, field extraction, and explanation wording. It is **never** the validation authority - all verdicts come from the existing `QuotationRuleEngine`.

## 2. Information Requested from IT / AI Platform

| # | Item | Environment variable | Example format (placeholder only) | Status |
|---:|---|---|---|---|
| 1 | Azure OpenAI endpoint | `AZURE_OPENAI_ENDPOINT` | `https://<resource-name>.openai.azure.com/` | Pending |
| 2 | Deployment name | `AZURE_OPENAI_DEPLOYMENT` | e.g. a GPT-4-class chat deployment | Pending |
| 3 | API version | `AZURE_OPENAI_API_VERSION` | e.g. `2024-06-01` | Pending |
| 4 | Authentication method | `AZURE_OPENAI_API_KEY` **or** Entra ID (managed identity / `DefaultAzureCredential`) | Key via secret store, never committed | Pending |
| 5 | Quota / rate limit | n/a | Tokens-per-minute and requests-per-minute for the deployment | Pending |
| 6 | Network access path | n/a | Public endpoint, private endpoint, or via API gateway | Pending |

Preferred authentication: **Entra ID / managed identity** where available; API key only as fallback, stored in `.env` (gitignored) or Streamlit `secrets.toml` (gitignored).

## 3. Intended Usage Scope (for the approval request)

| Aspect | Detail |
|---|---|
| Use cases | Intent extraction, quote field extraction, explanation wording |
| Not used for | Final validation decisions (rule engine remains authority) |
| Expected volume | Low - internal Beta demo, single user, ~10-100 requests/day |
| Model class | One chat-completion deployment is sufficient for the pilot |
| Data sent | User quote questions and extracted fields; product/rule data scope pending subphase 03 approval |

## 4. Configuration Convention in This Repository

- Local configuration lives in `.env` (gitignored). A template is provided at `.env.example` with placeholders only.
- Streamlit deployments may alternatively use `.streamlit/secrets.toml` (gitignored).
- No endpoint, key, or deployment name is ever committed to the repository.

## 5. Verification Steps (once access is granted)

1. Copy `.env.example` to `.env` and fill in the values provided by IT.
2. Send one minimal chat-completion request to the deployment and confirm an HTTP 200 response.
3. Record the confirmed endpoint owner, quota, and API version in this document (update the Status column).
4. Do not proceed to Phase 2 (reasoning layer integration) until subphase 03 (data usage approval) is also confirmed.

## 6. Open Questions for IT / AI Platform

1. Is an Azure OpenAI resource already provisioned that this pilot can share, or is a new resource required?
2. Which authentication method is mandated: Entra ID or API key?
3. Are there region restrictions on the Azure OpenAI resource for our data?
4. What is the approval path if quota needs to increase after the pilot?

## 7. Deliverable Status

| Deliverable | Status |
|---|---|
| Access request checklist (this document) | Done |
| Configuration template (`.env.example`) | Done |
| Confirmed endpoint / deployment / API version from IT | Pending IT response |
| Verified test call | Blocked until access granted |
