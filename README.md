# Quotation Bot

Quotation Bot is a rule-backed quotation assistant prototype for DRX-Compass configuration support. It combines structured product data, deterministic validation rules, and a lightweight web frontend to recommend quotation items from a natural-language request.

The current MVP can parse keyword-based requests, suggest a main model plus compatible options, and validate selected items against the implemented rule engine. It does not yet perform LLM-style reasoning or advanced semantic planning because no external reasoning API is integrated.

## Current Capabilities

- Natural-language keyword matching for quotation requests.
- Main model and accessory recommendation from `quotation_snapshot.json`.
- FastAPI backend for health checks and recommendation requests.
- Static HTML/CSS/JavaScript frontend for local demos.
- Streamlit chatbot-style prototype.
- Editable quotation table with deterministic discount approval.
- In-memory quotation Excel, approval Excel, and customer PDF exports.
- Local manager approval simulation for discounts above 35%.
- Deterministic rule checks for:
  - product region limits,
  - system combination compatibility,
  - detector/grid support,
  - generator/tube specification lookup.
- Rule review assets for candidate rules that still need SME confirmation.
- Demo output generation scripts for client-facing and internal audit samples.

## Project Structure

```text
app/                 Core Python application code
frontend/            Static web frontend
rules/               Confirmed, merged, normalized, and review-needed rules
docs/                Project documentation and meeting/supporting materials
scripts/             Demo, export, normalization, and presentation scripts
tests/               Unit tests for API, recommender, and rule engine
quotation_snapshot.json  Source snapshot used by the MVP
requirements.txt     Python runtime dependencies
streamlit_app.py     Streamlit prototype entry point
```

## Requirements

- Python 3.11 or newer
- pip

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run the FastAPI Backend

From the repository root:

```powershell
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Expected response:

```json
{
  "status": "ok"
}
```

## Run the Web Frontend

In a second terminal:

```powershell
cd frontend
python -m http.server 5173 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173
```

The frontend calls the backend at `http://127.0.0.1:8000`.

## Run the Streamlit Prototype

```powershell
streamlit run streamlit_app.py
```

`streamlit_app.py` is also the Streamlit Community Cloud entry point. The
demonstration uses local catalog matching and session state only; it does not
require an API key, database, or external AI service.

Use **Demo A - Auto Approval** for the 30% flow or **Demo B - Manager
Approval** for the 40% flow.

## API Usage

Recommendation endpoint:

```http
POST /recommend
Content-Type: application/json

{
  "message": "I need a FMT digital X-ray system for US with Focus detector, wall stand, and table."
}
```

The response includes a natural-language answer and the structured recommendation payload.

## CLI Examples

Search products:

```powershell
python -m app.cli search "Focus detector" --limit 5
```

Validate a configuration:

```powershell
python -m app.cli check --region US --product-id 6704878 --product-id 8620148
```

## Tests

Run the unit test suite:

```powershell
python -m unittest
```

Run focused tests:

```powershell
python -m unittest tests.test_rule_engine tests.test_recommender tests.test_api
```

## Demo Workflow

Generate the standard demo outputs:

```powershell
python .\scripts\run_demo_workflow.py
```

Generated files are treated as local artifacts and are ignored by default when preparing the repository for GitHub.

## Rule Coverage

Implemented executable rule categories are documented in `docs/rule_inventory.md`.

Current executable rules cover:

- product region allow/block behavior,
- system compatibility matrix results,
- detector/grid support checks,
- generator/tube specification lookup.

Candidate areas that still need business review include mandatory accessories, option cardinality, feature requirements, detector/bucky matching, business reasonableness, and escalation policy.

## Current Limitations

- Recommendations are keyword-based, not true reasoning.
- No external LLM or reasoning API is integrated yet.
- Some free-text and candidate rules require sales or SME review before they should become hard validation rules.
- Historical quote frequency and commercial fit are not yet modeled.

## Suggested GitHub Launch Notes

Use a private repository if the snapshot, product catalog, or rule files contain internal or proprietary data.

Before publishing, review:

- `quotation_snapshot.json`
- `rules/`
- `docs/`
- generated sample files

for any information that should not be shared publicly.
