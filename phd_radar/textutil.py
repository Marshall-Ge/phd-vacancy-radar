"""文本、日期与匹配工具。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .timeutil import KST, now_utc

PHD_PATTERN = re.compile(
    r"\b(ph\.?d|doctoral|doctorate|doktorand|doktorandin|promotion|studentship|research student)\b",
    re.I,
)

FUNDED_PATTERN = re.compile(
    r"\b(fully funded|funded|salaried|salary|gross|employment contract|tv-l|e\d{1,2}|"
    r"4[- ]year|four[- ]year|scholarship|stipend|fellowship|bezahlt|vollfinanziert)\b",
    re.I,
)

NEGATIVE_PATTERN = re.compile(
    r"\b(self[- ]funded|self[- ]financed|tuition fee|tuition fees|unpaid|no funding|"
    r"fee[- ]paying|selbstfinanziert|studiengebühren)\b",
    re.I,
)

HTML_TAG = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = HTML_TAG.sub(" ", value)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


TOPIC_SYNONYMS = {
    "information systems": ["information systems", "information system", "wirtschaftsinformatik", "is research"],
    "digital transformation": ["digital transformation", "digitalisation", "digitalization", "digitale transformation"],
    "digital strategy": ["digital strategy", "digital business strategy"],
    "data-driven decision": ["data-driven decision", "data driven decision", "data-driven management"],
    "data-driven management": ["data-driven management", "data driven management"],
    "business analytics": ["business analytics", "data analytics", "analytics"],
    "management and organization": ["management", "organization", "organisation", "organisational", "managerial"],
    "organizational behavior": ["organizational behavior", "organisational behaviour", "organizational behaviour"],
    "technology adoption": ["technology adoption", "technology acceptance", "adoption of technology"],
    "digital innovation": ["digital innovation", "innovation management", "innovation"],
    "decision support": ["decision support"],
    "digital business model": ["digital business model", "business model innovation"],
    "platform": ["platform economy", "digital platform", "platforms", "platform"],
    "AI adoption": ["ai adoption", "adoption of ai", "artificial intelligence adoption"],
    "artificial intelligence": ["artificial intelligence", "machine learning", " ai "],
    "Wirtschaftsinformatik": ["wirtschaftsinformatik"],
    "Digitalisierung": ["digitalisierung"],
    "Unternehmensführung": ["unternehmensführung", "unternehmensfuehrung"],
}


def _contains_variant(value: str, text: str) -> bool:
    value = normalize(value)
    if not value:
        return False
    # 短词（如 ai）用词边界，避免 certainty 里的 ai 误命中
    if len(value) <= 3:
        return re.search(r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])", text) is not None
    return value in text


def normalize_keyword_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("‑", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = value.replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def keyword_matches(keyword: str, normalized_text: str) -> bool:
    needle = normalize_keyword_text(keyword)
    if not needle:
        return False
    if len(needle) <= 3:
        return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", normalized_text) is not None
    return needle in normalized_text


def match_topics(text: str, topics: list[str]) -> list[str]:
    lowered = " " + normalize(text) + " "
    hits: list[str] = []
    for topic in topics:
        variants = TOPIC_SYNONYMS.get(topic, [normalize(topic)])
        if any(_contains_variant(v, lowered) for v in variants if v):
            hits.append(topic)
    return hits


def match_terms(text: str, terms: list[str]) -> list[str]:
    lowered = normalize(text)
    hits: list[str] = []
    for term in terms:
        needle = normalize(term)
        if needle and needle in lowered and term not in hits:
            hits.append(term)
    return hits


def is_phd_related(*values: str) -> bool:
    return bool(PHD_PATTERN.search(" ".join(v or "" for v in values)))


def has_funding_signal(text: str) -> bool:
    return bool(FUNDED_PATTERN.search(text or ""))


def has_negative_signal(text: str) -> bool:
    return bool(NEGATIVE_PATTERN.search(text or ""))


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_loose_date(value: str, *, now: datetime | None = None) -> datetime | None:
    """解析 '17 Oct' / '9 Nov ’26' / '31 Oct 2026' / '2026-10-17' 等。"""
    if not value:
        return None
    now = now or now_utc()
    text = value.replace("’", "'").replace("‘", "'").strip()

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
        except ValueError:
            return None

    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\.?(?:\s*'?(\d{2,4}))?", text)
    if m:
        day = int(m.group(1))
        month = _MONTHS.get(m.group(2).lower())
        if not month:
            return None
        year_raw = m.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            kst = now.astimezone(KST)
            year = kst.year
            candidate = datetime(year, month, day, tzinfo=KST)
            if candidate < kst - timedelta(days=180):
                year += 1
        try:
            return datetime(year, month, day, tzinfo=KST)
        except ValueError:
            return None
    return None


COUNTRY_HINTS = {
    "NL": ["netherlands", "amsterdam", "rotterdam", "delft", "eindhoven", "utrecht", "maastricht",
           "groningen", "tilburg", "leiden", "wageningen", "nijmegen", "enschede", "radboud", "erasmus"],
    "DK": ["denmark", "copenhagen", "aarhus", "odense", "dtu", "cbs", "roskilde", "aalborg"],
    "DE": ["germany", "munich", "münchen", "munchen", "berlin", "mannheim", "heidelberg", "hamburg",
           "cologne", "köln", "koln", "frankfurt", "stuttgart", "dresden", "tübingen", "tubingen",
           "bonn", "paderborn", "karlsruhe", "aachen", "göttingen", "gottingen", "wiesbaden"],
    "UK": ["united kingdom", "uk", "london", "oxford", "cambridge", "warwick", "lancaster",
           "edinburgh", "bristol", "bath", "manchester", "king's college", "ucl", "imperial",
           "nottingham", "sheffield", "southampton", "glasgow", "birmingham", "leeds", "york",
           "durham", "exeter", "sussex", "newcastle", "cardiff", "belfast"],
    "SE": ["sweden", "stockholm", "lund", "uppsala", "gothenburg", "göteborg", "kth", "chalmers"],
    "NO": ["norway", "oslo", "bergen", "trondheim", "bi norwegian"],
    "BE": ["belgium", "leuven", "ghent", "brussels", "antwerp"],
    "AT": ["austria", "vienna", "wien", "innsbruck", "graz"],
    "CH": ["switzerland", "zurich", "zürich", "basel", "bern", "epfl", "eth"],
    "FI": ["finland", "helsinki", "aalto", "turku"],
}


def infer_country(text: str, default: str = "UK") -> str:
    lowered = normalize(text)
    for code, hints in COUNTRY_HINTS.items():
        if any(hint in lowered for hint in hints):
            return code
    return default


def first_sentence(text: str, limit: int = 220) -> str:
    text = strip_html(text)
    if not text:
        return ""
    cut = re.split(r"(?<=[.!?])\s+", text)[0]
    cut = cut or text
    return cut[:limit].rstrip() + ("…" if len(cut) > limit else "")
