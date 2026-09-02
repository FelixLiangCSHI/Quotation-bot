from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.llm import get_llm_client, reasoning_status
from app.natural_language import parse_quote_request
from app.recommender import QuoteRecommender, render_recommendation_text
from app.serialization import to_jsonable


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
    message: str = Field(..., min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=30)
    max_accessories: int | None = Field(default=None, ge=1, le=200)


class RecommendResponse(BaseModel):
    answer: str
    recommendation: dict[str, Any]
    reasoning: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="Quotation Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_recommender() -> QuoteRecommender:
    return QuoteRecommender()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/llm/status")
def llm_status() -> dict[str, Any]:
    """Diagnostics for the Phase 2 reasoning layer (DeepSeek-v4-pro slot)."""
    return reasoning_status()


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
    return RecommendResponse(
        answer=answer,
        recommendation=to_jsonable(recommendation),
        reasoning={
            "llm_enabled": get_llm_client().enabled,
            "llm_fields_used": llm_fields_used,
            "llm_wording_used": llm_wording_used,
            "validation_authority": "QuotationRuleEngine",
        },
    )


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
    """Optionally polish answer wording; keep the deterministic text on failure."""
    client = get_llm_client()
    if not client.enabled:
        return answer, False
    polished = client.polish_explanation(answer, message)
    if not polished:
        return answer, False
    return polished, True


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