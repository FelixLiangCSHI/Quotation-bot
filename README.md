# AI Quotation Assistant Demo

A single-page offline Streamlit demonstration for sales quotation preparation.

## Demo Flow

Sales conversation
→ Local product configuration matching
→ Editable quotation
→ Discount approval check
→ Excel/PDF output

## Approval Rule

- Discount Rate ≤ 35%: automatically approved
- Discount Rate > 35%: manager approval required

The demo uses deterministic local matching and synthetic data.
No external AI API, SAP connection, database or email service is required.

## Run the Demo

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

`streamlit_app.py` is also the Streamlit Community Cloud entry point.

## Page Layout

The main page is conversation-first and renders vertically:

1. Header
2. Sales conversation workspace (full width)
3. Chat input
4. Contextual quick replies
5. Configuration summary
6. Quotation preview (full width, editable Quantity and Quotation Unit Price)
7. Discount approval
8. Output actions

The expanded sidebar holds the workspace controls: `New quotation`, the
workflow progress (Requirements → Configuration → Quotation → Approval), the
current draft summary, collapsed example requests and the system scope.

## Free Input Handling

- Greetings such as "I want to try." get a short invitation instead of a
  noisy recommendation.
- Missing information is requested one question at a time: customer, region,
  currency, main product and then discount rate.
- Quick reply buttons are converted to natural language and sent through the
  normal parser.
- Products outside the supported price book (DRX Compass, DRX Revolution,
  DRX Rise) never produce a quotation; the assistant asks the presenter to
  pick a supported system instead.

## Example Requests

Three neutral scenarios are available in the collapsed `Example requests`
section of the sidebar and behave exactly like typed user input:

- Hospital room upgrade
- Mobile imaging requirement
- Multi-system rollout

## Tests

```bash
python -m unittest discover -v
python -m compileall app streamlit_app.py
python scripts/smoke_test_demo.py
```

`tests/test_streamlit_presentation.py` covers the presentation helpers and the
multi-turn free-input flows without starting a browser.
`scripts/smoke_test_demo.py` verifies Demo A, Demo B and the "per system"
quantity scenario without starting a browser.

---

## Legacy Components

These components are kept for reference and are **not** required by the
Streamlit demo. Legacy API dependencies are stored separately in
`requirements-full.txt` and are not required for the Streamlit demo.

### FastAPI Backend

```bash
python -m pip install -r requirements-full.txt
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Recommendation endpoint:

```http
POST /recommend
Content-Type: application/json

{
  "message": "I need a FMT digital X-ray system for US with Focus detector, wall stand, and table."
}
```

### Static Frontend

```bash
cd frontend
python -m http.server 5173 --bind 127.0.0.1
```

Open `http://127.0.0.1:5173`. The frontend calls the backend at
`http://127.0.0.1:8000`.

### CLI

```bash
python -m app.cli search "Focus detector" --limit 5
python -m app.cli check --region US --product-id 6704878 --product-id 8620148
```

## Development Utilities

```bash
python scripts/run_demo_workflow.py
```

Other scripts in `scripts/` export and merge rule review files and build
presentation material. Generated files are treated as local artifacts and are
ignored by default.

## Reference Rule Assets

`rules/` holds confirmed, merged, normalized, and review-needed rules.
`docs/rule_inventory.md` documents the implemented executable rule categories:

- product region allow/block behavior,
- system compatibility matrix results,
- detector/grid support checks,
- generator/tube specification lookup.

Candidate areas that still need business review include mandatory accessories,
option cardinality, feature requirements, detector/bucky matching, business
reasonableness, and escalation policy. Roadmap and architecture notes live in
`docs/`.

## Project Structure

```text
app/                     Core Python application code
frontend/                Legacy static web frontend
rules/                   Rule assets
docs/                    Project documentation
scripts/                 Demo smoke test, export and presentation scripts
tests/                   Unit tests
quotation_snapshot.json  Synthetic product snapshot used by the demo
requirements.txt         Streamlit demo dependencies
requirements-full.txt    Full dependencies including the legacy FastAPI stack
streamlit_app.py         Streamlit demo entry point
.streamlit/config.toml   Streamlit theme configuration
```

## Current Limitations

- Recommendations are keyword-based, not true reasoning.
- No external LLM or reasoning API is integrated.
- Product, pricing and customer data in this repository is synthetic demo data.
- Manager approval is simulated in Streamlit session state only; it is not a
  persisted approval workflow.
