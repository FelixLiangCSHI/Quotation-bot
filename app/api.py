from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from app.llm import get_llm_client, reasoning_status
from app.data_loader import load_merged_rules_cached
from app.natural_language import parse_quote_request
from app.recommender import QuoteRecommender, render_recommendation_text
from app.serialization import to_jsonable

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
MAX_PRODUCT_IDS = 100

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)

PRODUCT_ID_FRAGMENT_RE = re.compile(r"\d{7}")
MONEY_FRAGMENT_RE = re.compile(r"\d[\d,]*\.\d{2}")

ProductId = Annotated[str, StringConstraints(min_length=1, max_length=40)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=100)]


REGION_VALUES = {
    "canada": "canada",
    "ca": "canada",
    "china": "china",
    "prc": "china",
    "eu": "eu",
    "europe": "eu",
    "italy": "italy",
    "italia": "italy",
    "it": "italy",
    "other": "other",
    "us": "us",
    "usa": "us",
    "u.s.": "us",
    "united states": "us",
}


class RecommendRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    region: str | None = Field(default=None, min_length=1, max_length=30)
    max_accessories: int | None = Field(default=None, ge=1, le=200)


class RecommendResponse(BaseModel):
    answer: str
    recommendation: dict[str, Any]
    reasoning: dict[str, Any] = Field(default_factory=dict)


class ValidationFields(BaseModel):
    """Structured validation input matching QuotationRuleEngine.check_configuration."""

    product_ids: list[ProductId] = Field(default_factory=list, max_length=MAX_PRODUCT_IDS)
    region: ShortText | None = None
    system_family: ShortText | None = None
    acquisition_type: ShortText | None = None
    tube_stand_id: ShortText | None = None
    wallstand_id: ShortText | None = None
    table_id: ShortText | None = None
    grid_id: ShortText | None = None
    grid_position: ShortText | None = None
    detector_type: ShortText | None = None
    generator: ShortText | None = None
    tube_spec: ShortText | None = None
    spec_category: ShortText | None = None


class ValidationCheckRequest(BaseModel):
    """Input for POST /validation/check.

    Either a natural-language ``message`` (parsed into structured fields) or
    explicit ``fields`` must be provided. Explicit fields always override
    values parsed from the message.
    """

    message: str | None = Field(default=None, max_length=MAX_MESSAGE_LENGTH)
    fields: ValidationFields | None = None


class ValidationCheckResponse(BaseModel):
    status: str
    issues: list[dict[str, Any]]
    missing_fields: list[str]
    summary: dict[str, int]
    resolved_input: dict[str, Any]
    rule_artifacts: dict[str, Any]
    validation_authority: str = "QuotationRuleEngine"


def _cors_origins() -> list[str]:
    """CORS allowlist, overridable for deployment via QUOTATION_CORS_ORIGINS."""
    raw = os.getenv("QUOTATION_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def _include_sources() -> bool:
    """Whether internal source provenance is exposed in API responses.

    Defaults to on for the Beta demo; set QUOTATION_INCLUDE_SOURCES=0 for
    enterprise deployments to strip workbook/sheet/cell metadata.
    """
    return os.getenv("QUOTATION_INCLUDE_SOURCES", "1").strip().casefold() not in (
        "0",
        "false",
        "no",
    )


def _strip_sources(value: Any) -> Any:
    """Recursively remove ``source`` provenance objects from a response."""
    if isinstance(value, dict):
        return {
            key: _strip_sources(item)
            for key, item in value.items()
            if key != "source"
        }
    if isinstance(value, list):
        return [_strip_sources(item) for item in value]
    return value


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Load data artifacts at startup so broken files fail fast, not lazily."""
    artifacts = get_rule_artifacts()
    logger.info(
        "Quotation Bot API started: %d products, %d rule signals, %d confirmed rules",
        artifacts["quotation_snapshot"]["products"],
        artifacts["quotation_snapshot"]["rule_signals"],
        artifacts["merged_rules"]["confirmed_rule_count"],
    )
    yield


app = FastAPI(title="Quotation Bot API", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="ui")


@lru_cache(maxsize=1)
def get_recommender() -> QuoteRecommender:
    return QuoteRecommender()


@lru_cache(maxsize=1)
def get_rule_artifacts() -> dict[str, Any]:
    """Metadata about the loaded data + rule artifacts (Phase 3 subphase 02)."""
    snapshot = get_recommender().snapshot
    merged = load_merged_rules_cached()
    return {
        "quotation_snapshot": {
            "products": len(snapshot.products_by_id),
            "rule_signals": len(snapshot.rule_signals),
        },
        "merged_rules": {
            "confirmed_rule_count": merged.get("confirmed_rule_count", len(merged["rules"])),
            "human_approved_rule_count": merged.get("human_approved_rule_count", 0),
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness + readiness: verifies the data artifacts actually load."""
    try:
        get_rule_artifacts()
    except Exception as exc:  # pragma: no cover - only on broken data files
        logger.error("Health check failed to load data artifacts: %s", exc)
        raise HTTPException(status_code=503, detail="data artifacts unavailable")
    return {"status": "ok"}


@app.get("/llm/status")
def llm_status() -> dict[str, Any]:
    """Diagnostics for the Phase 2 reasoning layer (DeepSeek-v4-pro slot)."""
    return reasoning_status()


@app.get("/data/sources")
def data_sources() -> dict[str, Any]:
    """File-based data provenance (Phase 4: keep Beta data simple).

    The Beta version reads all product and rule data directly from JSON
    files - no database, search index, or vector store is involved.
    """
    snapshot = get_recommender().snapshot
    merged = load_merged_rules_cached()
    metadata = snapshot.raw.get("metadata", {})
    return {
        "storage": "file-based (JSON + Markdown)",
        "database": None,
        "search_index": None,
        "vector_index": None,
        "sources": {
            "quotation_snapshot.json": {
                "role": "product/data source",
                "snapshot_version": metadata.get("snapshot_version"),
                "generated_at": metadata.get("generated_at"),
                "source_file": metadata.get("source_file"),
                "products": len(snapshot.products_by_id),
                "rule_signals": len(snapshot.rule_signals),
            },
            "rules/merged_rules.json": {
                "role": "confirmed rule artifact",
                "confirmed_rule_count": merged.get("confirmed_rule_count"),
                "human_approved_rule_count": merged.get("human_approved_rule_count"),
            },
            "docs/*.md": {
                "role": "implementation notes and workflow explanation",
            },
        },
    }


@app.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message cannot be blank")

    quote_request = parse_quote_request(message)
    quote_request, llm_fields_used = _apply_llm_extraction(quote_request, message)
    region = _normalize_region(request.region)
    if region:
        quote_request = replace(quote_request, region=region)

    recommendation = get_recommender().recommend(
        quote_request,
        max_accessories=request.max_accessories,
    )
    answer = render_recommendation_text(recommendation)
    answer, llm_wording_used = _apply_llm_wording(answer, message)
    recommendation_payload = to_jsonable(recommendation)
    if not _include_sources():
        recommendation_payload = _strip_sources(recommendation_payload)
    return RecommendResponse(
        answer=answer,
        recommendation=recommendation_payload,
        reasoning={
            "llm_enabled": get_llm_client().enabled,
            "llm_fields_used": llm_fields_used,
            "llm_wording_used": llm_wording_used,
            "validation_authority": "QuotationRuleEngine",
        },
    )


@app.post("/validation/check", response_model=ValidationCheckResponse)
def validation_check(request: ValidationCheckRequest) -> ValidationCheckResponse:
    """Deterministic quote validation (Phase 3 deliverable).

    The QuotationRuleEngine is the single validation authority. A natural
    language ``message`` is converted into structured validation input;
    explicit ``fields`` always override parsed values. No LLM is involved.
    """
    resolved = _resolve_validation_input(request)
    if not resolved["product_ids"] and not any(
        value for key, value in resolved.items() if key != "product_ids"
    ):
        raise HTTPException(
            status_code=422,
            detail="provide a message or at least one validation field",
        )
    result = get_recommender().engine.check_configuration(**resolved)
    issues = [to_jsonable(issue) for issue in result.issues]
    if not _include_sources():
        issues = [_strip_sources(issue) for issue in issues]
    summary = {
        "errors": sum(1 for issue in result.issues if issue.severity == "error"),
        "warnings": sum(1 for issue in result.issues if issue.severity == "warning"),
        "infos": sum(1 for issue in result.issues if issue.severity == "info"),
    }
    return ValidationCheckResponse(
        status=result.status,
        issues=issues,
        missing_fields=list(result.missing_fields),
        summary=summary,
        resolved_input=resolved,
        rule_artifacts=get_rule_artifacts(),
    )


def _resolve_validation_input(request: ValidationCheckRequest) -> dict[str, Any]:
    """Convert message + explicit fields into check_configuration kwargs.

    Message parsing supplies region/system_family/acquisition_type/product ids;
    explicit structured fields take precedence over parsed values.
    """
    resolved: dict[str, Any] = {
        "product_ids": [],
        "region": None,
        "system_family": None,
        "acquisition_type": None,
        "tube_stand_id": None,
        "wallstand_id": None,
        "table_id": None,
        "grid_id": None,
        "grid_position": None,
        "detector_type": None,
        "generator": None,
        "tube_spec": None,
        "spec_category": None,
    }
    message = (request.message or "").strip()
    if message:
        parsed = parse_quote_request(message)
        resolved["product_ids"] = list(parsed.product_ids)
        resolved["region"] = parsed.region
        resolved["system_family"] = parsed.system_family
        resolved["acquisition_type"] = parsed.acquisition_type
    if request.fields is not None:
        fields = request.fields
        if fields.product_ids:
            merged_ids = list(
                dict.fromkeys(list(resolved["product_ids"]) + list(fields.product_ids))
            )
            resolved["product_ids"] = merged_ids
        if fields.region:
            resolved["region"] = _normalize_region(fields.region)
        for key in (
            "system_family",
            "acquisition_type",
            "tube_stand_id",
            "wallstand_id",
            "table_id",
            "grid_id",
            "grid_position",
            "detector_type",
            "generator",
            "tube_spec",
            "spec_category",
        ):
            value = getattr(fields, key)
            if value:
                resolved[key] = value.strip()
    return resolved


def _apply_llm_extraction(quote_request, message: str):
    """Fill fields the deterministic parser missed using the LLM.

    The LLM only supplements missing fields - deterministic extraction always
    wins, and validation stays with the rule engine.
    """
    client = get_llm_client()
    if not client.enabled:
        return quote_request, False
    needs_fields = not (
        quote_request.region
        and quote_request.system_family
        and quote_request.acquisition_type
    )
    if not needs_fields:
        return quote_request, False
    fields = client.extract_fields(message)
    if not fields:
        return quote_request, False
    updates: dict[str, Any] = {}
    for key in ("region", "system_family", "acquisition_type"):
        if getattr(quote_request, key) is None and fields.get(key):
            updates[key] = fields[key]
    extra_ids = tuple(
        pid
        for pid in fields.get("product_ids", ())
        if pid not in quote_request.product_ids
    )
    if extra_ids:
        updates["product_ids"] = quote_request.product_ids + extra_ids
    if not updates:
        return quote_request, False
    return replace(quote_request, **updates), True


def _apply_llm_wording(answer: str, message: str) -> tuple[str, bool]:
    """Optionally polish answer wording; keep the deterministic text on failure.

    The polished text is treated as untrusted: it is only accepted when every
    product ID, price, and the validation verdict from the deterministic
    answer are preserved (guards against prompt-injected rewrites).
    """
    client = get_llm_client()
    if not client.enabled:
        return answer, False
    polished = client.polish_explanation(answer, message)
    if not polished:
        return answer, False
    if not _polish_preserves_facts(answer, polished):
        logger.warning(
            "LLM-polished answer dropped or altered facts; keeping deterministic text"
        )
        return answer, False
    return polished, True


def _polish_preserves_facts(original: str, polished: str) -> bool:
    """True when ``polished`` keeps all critical facts from ``original``."""
    for product_id in set(PRODUCT_ID_FRAGMENT_RE.findall(original)):
        if product_id not in polished:
            return False
    for amount in set(MONEY_FRAGMENT_RE.findall(original)):
        if amount not in polished:
            return False
    original_blocking = "blocking issue found" in original.casefold()
    polished_blocking = "blocking" in polished.casefold()
    if original_blocking and not polished_blocking:
        return False
    if not original_blocking and "blocking issue found" in polished.casefold():
        return False
    return True


def _normalize_region(region: str | None) -> str | None:
    if region is None:
        return None
    normalized = region.strip().casefold()
    if not normalized:
        return None
    canonical = REGION_VALUES.get(normalized)
    if canonical is None:
        raise HTTPException(status_code=422, detail=f"unsupported region: {region}")
    return canonical