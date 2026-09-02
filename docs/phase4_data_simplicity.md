# Phase 4 - Keep Beta Version Data Simple (Execution Log)

Status: **Complete - Beta data stays file-based; database/search/embedding are
explicitly deferred with written trigger conditions.**

## Subphase execution

| Subphase | Roadmap item | Result | Status |
|---:|---|---|---|
| 01 | Continue using `quotation_snapshot.json` as the product/data source | Confirmed: `app/data_loader.py` (`load_snapshot()`) is the only product data path; snapshot v0.1.0 generated from `quotation_data.xlsx` (openxml read-only), 380 catalog products (191 with ids in `products_by_id`), 984 rule signals. New `GET /data/sources` endpoint exposes this provenance | Done |
| 02 | Continue using `rules/merged_rules.json` as the rule artifact | Confirmed: 700 confirmed rules loaded via `load_merged_rules()` (added in Phase 3); artifact metadata surfaced in both `/validation/check` (`rule_artifacts`) and `/data/sources` | Done |
| 03 | Use Markdown docs for implementation notes and workflow explanation | Confirmed: all planning/execution records live in `docs/*.md` (Phase 0-4 logs, roadmap, implementation flow, rule inventory/review workflow); no wiki/db-backed docs introduced | Done |
| 04 | Add database/search only when the pilot needs it | Decision recorded below; dependency audit confirms **zero** database, search-index, or vector/embedding dependencies in `app/`, `frontend/`, and `requirements*.txt` | Done |

## Data decision record (subphase 04)

Beta version decision: **file-based only**. `requirements.txt` contains just
fastapi, uvicorn, openpyxl, reportlab - no DB driver, no search library, no
embedding/vector store.

| Data option | Beta decision | Deferred until (trigger condition) |
|---|---|---|
| JSON files (`quotation_snapshot.json`, `rules/*.json`) | **Use now** | Keep while single-user pilot; move behind an API/DB when refresh control or audit trail is required |
| Markdown files (`docs/*.md`) | **Use now** for notes/workflow | Optional knowledge base later |
| SQL / internal DB | **Not used** | Multi-user concurrent access, controlled data refresh, audit requirements, or snapshot size hurting startup time |
| Search index | **Not used** | Keyword search quality proves insufficient during pilot UAT |
| Embedding / vector index | **Not used** | A validated need for semantic product search emerges from pilot feedback |

These options are later-stage improvements, **not Beta blockers**.

## Deliverables

1. **File-based Beta data loader** - `app/data_loader.py`:
   `load_snapshot()` + `QuotationSnapshot` (products, rule signals,
   compatibility/detector-grid/generator-tube matrices) and
   `load_merged_rules()` (confirmed rule artifact). All consumers
   (recommender, rule engine, API) read exclusively through it.
2. **Provenance endpoint** - `GET /data/sources` returns the storage mode,
   explicit `null` for database/search/vector, and per-file role + metadata
   (snapshot version, generation timestamp, source workbook, counts).
3. **This decision record.**

## Verification

- Dependency audit: `grep` across `app/`, `frontend/`, `requirements*.txt`
  found no sqlalchemy/sqlite/postgres/mysql/elasticsearch/redis/
  chromadb/faiss/embedding/vector references.
- New suite `tests/test_data_sources_api.py` (4 tests) - storage mode,
  snapshot provenance, rule artifact, docs role.
- Full regression: **169 tests + 40 subtests pass**.
