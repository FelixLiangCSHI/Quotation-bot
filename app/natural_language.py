from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteRequest:
    raw_text: str
    keywords: tuple[str, ...]
    product_ids: tuple[str, ...]
    region: str | None = None
    system_family: str | None = None
    acquisition_type: str | None = None


PRODUCT_ID_RE = re.compile(r"\b\d{7}\b")
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+/-]*|\d+(?:kw|khu|ft|cm|li)?", re.IGNORECASE)
DISCOUNT_PERCENT_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(?:%|percent\b)",
    re.IGNORECASE,
)

# A percentage only counts as a discount when one of these markers sits next to
# it. This keeps payment terms and taxes out of the discount rate.
DISCOUNT_MARKER_RE = re.compile(
    r"(?<![a-z])(?:discount|discounted|off|rebate)(?![a-z])|折扣|优惠|减价",
    re.IGNORECASE,
)
NON_DISCOUNT_MARKER_RE = re.compile(
    r"(?<![a-z])(?:deposit|down\s*payment|downpayment|prepayment|tax|vat|gst|"
    r"installation|commissioning|completion|delivery|retention|milestone|"
    r"advance|interest|shipping)(?![a-z])|定金|首付|税|安装|尾款",
    re.IGNORECASE,
)
BARE_PERCENT_RE = re.compile(
    r"^\W*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\W*$",
    re.IGNORECASE,
)

# Characters scanned around a percentage when looking for context markers.
DISCOUNT_CONTEXT_WINDOW = 32

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "i",
    "in",
    "is",
    "me",
    "need",
    "of",
    "one",
    "please",
    "recommend",
    "budget",
    "cost",
    "price",
    "rmb",
    "cny",
    "usd",
    "eur",
    "the",
    "to",
    "want",
    "with",
}

REGION_ALIASES = (
    ("canada", ("canada", "加拿大")),
    ("china", ("china", "prc", "中国", "中国市场")),
    ("us", ("u.s.", "us", "usa", "united states", "america", "美国", "美区")),
    ("eu", ("europe", "eu", "emea", "欧洲", "欧盟")),
)

SYSTEM_FAMILY_ALIASES = (
    ("OTC", ("otc", "overhead", "ceiling", "悬吊", "天吊", "吊架")),
    ("FMT", ("fmt", "floor mount", "floor-mounted", "floor mounted", "落地", "地轨", "立柱")),
)

ACQUISITION_ALIASES = (
    ("digital", ("digital", "dr", "数字", "数字化")),
    ("analog", ("analog", "analogue", "模拟")),
)

PHRASE_KEYWORDS = (
    ("x-ray", ("xray", "x-ray", "x ray", "x光", "x 射线", "放射")),
    ("system", ("system", "系统", "整机", "整套", "配置")),
    ("detector", ("detector", "探测器", "平板")),
    ("generator", ("generator", "发生器", "高压发生器")),
    ("tube", ("tube", "球管")),
    ("collimator", ("collimator", "限束器", "束光器")),
    ("wallstand", ("wallstand", "wall stand", "胸片架", "壁架", "立位架")),
    ("table", ("table", "摄影床", "检查床", "床")),
    ("grid", ("grid", "滤线栅")),
    ("bucky", ("bucky", "暗盒架")),
    ("wireless", ("wireless", "wifi", "wi-fi", "无线")),
    ("manual", ("manual", "手动")),
    ("motorized", ("motorized", "motorised", "电动", "马达")),
    ("focus", ("focus", "focus 35", "focus 43")),
    ("drx", ("drx", "drx plus", "drx lux")),
    ("low-cost", ("low cost", "cost effective", "便宜", "低价", "经济", "预算有限")),
)


def parse_quote_request(text: str) -> QuoteRequest:
    raw_text = text.strip()
    return QuoteRequest(
        raw_text=raw_text,
        keywords=_extract_keywords(raw_text),
        product_ids=tuple(dict.fromkeys(PRODUCT_ID_RE.findall(raw_text))),
        region=_extract_region(raw_text),
        system_family=_extract_system_family(raw_text),
        acquisition_type=_extract_acquisition_type(raw_text),
    )


def parse_discount_rate(text: str, *, allow_bare_percentage: bool = True) -> float | None:
    """Return the discount rate expressed in ``text`` as a fraction.

    A percentage is only treated as a discount when a discount marker sits next
    to it (``discount``, ``off``, ``折扣`` ...). Percentages that belong to
    payment terms or taxes are ignored. When ``allow_bare_percentage`` is true a
    final line that only contains a percentage is accepted as well, which covers
    the case where the assistant already asked for the discount rate.
    """
    explicit = _explicit_discount_rates(text)
    if explicit:
        return explicit[-1]
    if allow_bare_percentage:
        return _bare_percentage_answer(text)
    return None


def _explicit_discount_rates(text: str) -> list[float]:
    rates: list[float] = []
    for match in DISCOUNT_PERCENT_RE.finditer(text):
        if _is_discount_percentage(text, match.start(), match.end()):
            rates.append(float(match.group(1)) / 100)
    return rates


def _is_discount_percentage(text: str, start: int, end: int) -> bool:
    """Decide whether a percentage close to ``start`` describes a discount.

    The nearest marker wins, so "a 30% deposit applies and a 25% discount"
    only yields the 25% value.
    """
    window = text[max(0, start - DISCOUNT_CONTEXT_WINDOW) : end + DISCOUNT_CONTEXT_WINDOW]
    offset = start - max(0, start - DISCOUNT_CONTEXT_WINDOW)
    discount_distance = _nearest_marker_distance(window, DISCOUNT_MARKER_RE, offset)
    excluded_distance = _nearest_marker_distance(window, NON_DISCOUNT_MARKER_RE, offset)
    if discount_distance is None:
        return False
    return excluded_distance is None or discount_distance < excluded_distance


def _nearest_marker_distance(
    window: str,
    marker: re.Pattern[str],
    offset: int,
) -> int | None:
    distances = [abs(match.start() - offset) for match in marker.finditer(window)]
    return min(distances) if distances else None


def _bare_percentage_answer(text: str) -> float | None:
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        match = BARE_PERCENT_RE.match(candidate)
        return float(match.group(1)) / 100 if match else None
    return None


def _extract_region(text: str) -> str | None:
    normalized = text.casefold()
    for region, aliases in REGION_ALIASES:
        if _contains_any(normalized, aliases):
            return region
    return None


def _extract_system_family(text: str) -> str | None:
    normalized = text.casefold()
    for system_family, aliases in SYSTEM_FAMILY_ALIASES:
        if _contains_any(normalized, aliases):
            return system_family
    return None


def _extract_acquisition_type(text: str) -> str | None:
    normalized = text.casefold()
    for acquisition_type, aliases in ACQUISITION_ALIASES:
        if _contains_any(normalized, aliases):
            return acquisition_type
    return None


def _extract_keywords(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    keywords: list[str] = []

    for keyword, aliases in PHRASE_KEYWORDS:
        if _contains_any(normalized, aliases):
            keywords.append(keyword)

    for value in (_extract_system_family(text), _extract_acquisition_type(text)):
        if value:
            keywords.append(value.casefold())

    for token in WORD_RE.findall(normalized):
        clean_token = token.strip(".,;:!?()[]{}\"'").casefold()
        if (
            clean_token
            and len(clean_token) > 1
            and clean_token not in STOP_WORDS
            and not clean_token.isdigit()
            and not PRODUCT_ID_RE.fullmatch(clean_token)
        ):
            keywords.append(clean_token)

    return tuple(dict.fromkeys(keywords))


def _contains_any(text: str, aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        normalized_alias = alias.casefold()
        if re.fullmatch(r"[a-z0-9. -]+", normalized_alias):
            pattern = r"(?<![a-z0-9])" + re.escape(normalized_alias) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                return True
        elif normalized_alias in text:
            return True
    return False