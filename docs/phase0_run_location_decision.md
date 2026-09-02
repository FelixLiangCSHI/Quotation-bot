# Phase 0 / Subphase 04 - Demo Run Location Decision

Date: 2026-09-02
Status: Recommendation prepared - awaiting IT confirmation
Source references: `docs/quotation_bot_mvp_vs_production_architecture.md` (Phase 0 item 4), `docs/phase0_pilot_scope.md` (sign-off item 6), `docs/phase0_data_usage_approval.md`.

## 1. Purpose

Decide where the first demo runs: **locally**, on an **internal server**, or **behind an API gateway**. This choice affects who can access the demo, what IT approvals are needed, and how soon the pilot can start.

## 2. Current Technical Baseline

| Component | How it runs today |
|---|---|
| Streamlit demo (`streamlit_app.py`) | `streamlit run streamlit_app.py` on a laptop; also deployable to Streamlit Community Cloud (public SaaS) |
| FastAPI service (`app/api.py`) | `python -m uvicorn app.api:app --host 127.0.0.1 --port 8000` (localhost only; CORS limited to localhost origins) |
| Data | Local files only (`quotation_snapshot.json`, `rules/merged_rules.json`); no database, no external services |
| Azure OpenAI | Not yet connected (pending subphases 02/03 approvals) |

## 3. Option Comparison

| Criterion | Option A: Local laptop | Option B: Internal server / VM | Option C: Behind company API gateway |
|---|---|---|---|
| Audience | Presenter only (screen share for demos) | Pilot users on company network | Any approved frontend (Teams, Web App, Dify...) |
| IT approvals needed | None (plus Azure OpenAI egress once connected) | VM/host allocation, network rules, run-as account | Gateway onboarding, SSO/Entra ID, API contract |
| Setup effort | Minutes | Days | Weeks |
| Data exposure | None beyond the laptop | Company network only | Company network, centrally governed |
| Auth | Not needed | Recommended (at least network ACL) | Required (SSO / Entra ID) |
| Fits roadmap phase | Phase 0-1 (Beta demo) | Phase 6 pilot (multi-user) | Phase 6-7 (production APIs) |
| Risk | Lowest | Low | Deferred until API contract exists |

### Streamlit Community Cloud caution

`streamlit_app.py` currently supports Streamlit Community Cloud deployment. That is a **public SaaS host outside company control**. Under the Phase 0 data boundary, Community Cloud must **not** be used for any demo that connects to Azure OpenAI or uses non-synthetic company data. It remains acceptable only for the fully synthetic offline demo already in the README.

## 4. Recommendation

> **Option A - run the first demo locally** on the presenter's laptop (Streamlit UI + localhost FastAPI + local JSON files), with Azure OpenAI as the only outbound call once subphases 02/03 are approved.

Reasons:

1. Matches the roadmap: Phase 1 explicitly targets a *local* chat UI; server/gateway hosting is a Phase 6+ concern.
2. Zero infrastructure dependency: the demo can be shown immediately via screen share.
3. Smallest approval surface: only Azure OpenAI network egress needs sign-off, which is already being requested in subphase 02.
4. Data stays local, consistent with the subphase 03 boundary (files never leave the machine; only minimal per-turn prompt text goes to Azure OpenAI).

## 5. Escalation Path (when to move beyond local)

| Trigger | Move to |
|---|---|
| Pilot users need hands-on access (not just watching a demo) | Option B: internal server/VM with network ACL |
| `POST /validation/check` is consumed by another team or frontend | Option B first, then Option C once the API contract is reviewed |
| Production frontend decision made (Phase 7) | Option C: company API gateway with SSO/Entra ID |

## 6. Confirmations Needed from IT

| # | Question | Status |
|---:|---|---|
| 1 | Confirm a locally run demo (laptop, screen share) is acceptable for the first presentation | Pending |
| 2 | Confirm outbound HTTPS from the presenter's laptop to the approved Azure OpenAI endpoint is allowed | Pending |
| 3 | Confirm Streamlit Community Cloud is prohibited once real data or Azure OpenAI is connected | Pending |
| 4 | Identify the internal server/VM option to reserve for the Phase 6 pilot (name/owner only, no build yet) | Pending |

## 7. Deliverable Status

| Deliverable | Status |
|---|---|
| Option comparison and recommendation (this document) | Done |
| Escalation path to internal server / API gateway | Done |
| IT confirmation of local run + Azure OpenAI egress | Pending |

## 8. Phase 0 Completion Note

With this subphase, all four Phase 0 items have prepared deliverables:

| Subphase | Deliverable | Status |
|---:|---|---|
| 01 | Pilot scope (`docs/phase0_pilot_scope.md`) | Done - pending business sign-offs |
| 02 | Azure OpenAI access request (`docs/phase0_azure_openai_access_request.md`, `.env.example`) | Done - pending IT response |
| 03 | Data usage boundary (`docs/phase0_data_usage_approval.md`) | Done - pending security sign-off |
| 04 | Run location decision (this document) | Done - pending IT confirmation |

Next step once sign-offs land: **Phase 1 - Beta chat interface flow** (question -> extracted fields -> validation -> explanation), followed by exposing `POST /validation/check`.
