"""Phase 2 reasoning layer client (DeepSeek-v4-pro enterprise API slot).

This module reserves the integration port for the enterprise reasoning API.
It talks to any OpenAI-compatible ``/chat/completions`` endpoint and is used
only for:

1. Intent / field extraction (fills fields the deterministic parser missed).
2. Explanation wording (optional polish of the deterministic answer).

It is **never** the validation authority - ``QuotationRuleEngine`` remains the
single source of truth. When the API is not configured or any call fails, the
caller falls back to the deterministic pipeline, so the bot keeps working
without the LLM.

Data boundary (Phase 0 approval): only the user's question text and per-turn
extracted fields are sent. Product JSON files, pricing, and workbook comments
must never be included in prompts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_TIMEOUT_SECONDS = 15.0

ALLOWED_REGIONS = {"canada", "china", "eu", "italy", "other", "us"}
ALLOWED_SYSTEM_FAMILIES = {"OTC", "FMT"}
ALLOWED_ACQUISITION_TYPES = {"digital", "analog"}
PRODUCT_ID_RE = re.compile(r"^\d{7}$")

EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured fields from an X-ray equipment quotation request. "
    "Reply with a single JSON object and nothing else, using exactly these "
    "keys: region (one of canada, china, eu, italy, other, us, or null), "
    "system_family (OTC or FMT, or null), acquisition_type (digital or "
    "analog, or null), product_ids (array of 7-digit strings). Use null when "
    "the user did not state the value. Never guess or invent values."
)

EXPLANATION_SYSTEM_PROMPT = (
    "You rewrite a quotation bot's answer so it is clear and professional. "
    "Keep every fact, product id, price, and validation verdict exactly as "
    "given. Do not add, remove, or change any recommendation or verdict. "
    "Reply with the rewritten answer only."
)


@dataclass(frozen=True)
class LLMConfig:
    """Connection settings for the enterprise reasoning API."""

    base_url: str
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = (
            os.getenv("LLM_API_BASE") or os.getenv("DEEPSEEK_API_BASE") or ""
        ).strip().rstrip("/")
        if base_url and not base_url.startswith("https://"):
            # Fail closed: never send the API key over plain HTTP or to a
            # malformed endpoint. The reasoning layer stays disabled instead.
            logger.warning(
                "LLM_API_BASE must use https:// - reasoning layer disabled "
                "(got %r)",
                base_url,
            )
            base_url = ""
        api_key = (
            os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
        ).strip()
        model = (os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
        try:
            timeout_seconds = float(
                os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
            )
        except ValueError:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


class LLMClient:
    """Minimal OpenAI-compatible chat client with graceful degradation."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str | None:
        """Return the assistant reply text, or ``None`` on any failure."""
        if not self.enabled:
            return None
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.config.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning("LLM call failed, falling back: %s", exc)
            return None
        return content if isinstance(content, str) else None

    def extract_fields(self, message: str) -> dict[str, object] | None:
        """Extract quotation fields from ``message``.

        Returns a sanitized dict with keys ``region``, ``system_family``,
        ``acquisition_type`` and ``product_ids``, or ``None`` when the LLM is
        unavailable or returned an unusable reply. Values outside the allowed
        vocabularies are dropped so a hallucinated value can never reach the
        rule engine.
        """
        reply = self.chat(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        if reply is None:
            return None
        parsed = _parse_json_object(reply)
        if parsed is None:
            return None
        return _sanitize_fields(parsed)

    def polish_explanation(self, answer: str, question: str) -> str | None:
        """Return a polished wording of ``answer``, or ``None`` on failure."""
        reply = self.chat(
            [
                {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User question:\n{question}\n\n"
                        f"Bot answer to rewrite:\n{answer}"
                    ),
                },
            ],
            temperature=0.2,
        )
        if reply is None:
            return None
        polished = reply.strip()
        return polished or None


def _parse_json_object(text: str) -> dict[str, object] | None:
    """Parse a JSON object from ``text``, tolerating code fences."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = re.sub(r"\n?```$", "", candidate).strip()
    try:
        parsed = json.loads(candidate)
    except ValueError:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _sanitize_fields(raw: dict[str, object]) -> dict[str, object]:
    """Keep only values inside the closed vocabularies."""
    fields: dict[str, object] = {
        "region": None,
        "system_family": None,
        "acquisition_type": None,
        "product_ids": (),
    }
    region = raw.get("region")
    if isinstance(region, str) and region.strip().casefold() in ALLOWED_REGIONS:
        fields["region"] = region.strip().casefold()
    system_family = raw.get("system_family")
    if (
        isinstance(system_family, str)
        and system_family.strip().upper() in ALLOWED_SYSTEM_FAMILIES
    ):
        fields["system_family"] = system_family.strip().upper()
    acquisition_type = raw.get("acquisition_type")
    if (
        isinstance(acquisition_type, str)
        and acquisition_type.strip().casefold() in ALLOWED_ACQUISITION_TYPES
    ):
        fields["acquisition_type"] = acquisition_type.strip().casefold()
    product_ids = raw.get("product_ids")
    if isinstance(product_ids, (list, tuple)):
        fields["product_ids"] = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in product_ids
                if PRODUCT_ID_RE.match(str(item).strip())
            )
        )
    return fields


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient(LLMConfig.from_env())


def reasoning_status() -> dict[str, object]:
    """Status of the reasoning layer for diagnostics endpoints."""
    client = get_llm_client()
    return {
        "enabled": client.enabled,
        "provider": "deepseek" if client.enabled else None,
        "model": client.config.model if client.enabled else None,
        "role": "intent/field extraction and explanation wording only",
        "validation_authority": "QuotationRuleEngine",
    }
