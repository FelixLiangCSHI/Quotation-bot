# AI Quotation Assistant Demo

An offline demonstration for sales quotation preparation with a static web
frontend (`frontend/`) backed by a local FastAPI service (`app/api.py`).

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
No SAP connection, database or email service is required. An optional
reasoning layer (enterprise DeepSeek-v4-pro, OpenAI-compatible) can be
enabled via environment variables; without it the bot runs fully offline.

## Run the Demo

Start the FastAPI backend:

```bash
pip install -r requirements.txt
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Serve the static web frontend in a second terminal:

```bash
cd frontend
python -m http.server 5173 --bind 127.0.0.1
```

Open `http://127.0.0.1:5173`. The frontend calls the backend at
`http://127.0.0.1:8000`.

## Free Input Handling

- Greetings such as "I want to try." get a short invitation instead of a
  noisy recommendation.
- Missing information is requested one question at a time: customer, region,
  currency, main product and then discount rate.
- Quick replies are converted to natural language and sent through the
  normal parser (see `app/conversation.py`).
- Products outside the supported price book (DRX Compass, DRX Revolution,
  DRX Rise) never produce a quotation; the assistant asks the presenter to
  pick a supported system instead.

## Example Requests

Three neutral scenarios are defined in `app/conversation.py`
(`EXAMPLE_REQUESTS`) and behave exactly like typed user input:

- Hospital room upgrade
- Mobile imaging requirement
- Multi-system rollout

## Tests

```bash
python -m unittest discover -v
python -m compileall app
python scripts/smoke_test_demo.py
```

`tests/test_conversation.py` covers the conversation helpers and the
multi-turn free-input flows without starting a browser.
`scripts/smoke_test_demo.py` verifies Demo A, Demo B and the "per system"
quantity scenario without starting a browser.

---

## API

Recommendation endpoint:

```http
POST /recommend
Content-Type: application/json

{
  "message": "I need a FMT digital X-ray system for US with Focus detector, wall stand, and table."
}
```

Deterministic validation endpoint (Phase 3, see
`docs/phase3_validation_authority.md`) - the rule engine is the validation
authority; no LLM is involved:

```http
POST /validation/check
Content-Type: application/json

{
  "message": "Can I quote product 6703656 for the EU?",
  "fields": {"region": "us"}
}
```

Returns `status` (valid / invalid / incomplete), issues with
error/warning/info severity, missing fields, and rule artifact metadata.
Explicit `fields` override values parsed from `message`.

Reasoning-layer diagnostics (Phase 2, see `docs/phase2_reasoning_layer.md`):

```http
GET /llm/status
```

The reasoning layer is disabled by default. To enable it, set `LLM_API_BASE`
and `LLM_API_KEY` (see `.env.example`). It is used only for field extraction
and explanation wording - validation is always done by the rule engine.

Development extras (test client, etc.) live in `requirements-full.txt`:

```bash
python -m pip install -r requirements-full.txt
```

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
app/                     Core Python application code (incl. FastAPI service)
frontend/                Static web frontend (Beta UI)
rules/                   Rule assets
docs/                    Project documentation
scripts/                 Demo smoke test, export and presentation scripts
tests/                   Unit tests
quotation_snapshot.json  Synthetic product snapshot used by the demo
requirements.txt         Runtime dependencies (FastAPI backend)
requirements-full.txt    Full dependencies including development extras
```

## Current Limitations

- Recommendations are keyword-based, not true reasoning.
- The reasoning layer (DeepSeek-v4-pro) is integrated but disabled until
  enterprise credentials are configured; it never overrides the rule engine.
- Product, pricing and customer data in this repository is synthetic demo data.
- Manager approval is simulated in the current browser session only; it is
  not a persisted approval workflow.
