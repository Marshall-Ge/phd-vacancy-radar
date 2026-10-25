"""匹配评分与板块归类。"""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import Profile, Section
from .models import Award, Position
from .textutil import (
    has_funding_signal,
    has_negative_signal,
    is_phd_related,
    keyword_matches,
    match_terms,
    normalize,
    normalize_keyword_text,
)


def _sections(profile: Profile, sections: list[Section] | None) -> list[Section]:
    if sections:
        return sections
    return [Section(key="A", name="目标方向", keywords=profile.topics, priority=1)]


def _match_by_section(text: str, sections: list[Section]) -> dict[str, list[str]]:
    normalized = normalize_keyword_text(text)
    result: dict[str, list[str]] = {}
    for section in sections:
        hits = [kw for kw in section.keywords if keyword_matches(kw, normalized)]
        if hits:
            result[section.key] = hits
    return result


def _pick_section(hits: dict[str, list[str]], sections: list[Section]) -> tuple[Section | None, list[str]]:
    research = [s for s in sections if s.key in {"A", "B", "C"} and s.key in hits]
    if research:
        best = max(research, key=lambda s: (len(hits[s.key]), -s.priority))
        return best, hits[best.key]
    if "D" in hits:
        section = next((s for s in sections if s.key == "D"), None)
        if section is not None:
            return section, hits["D"]
    return None, []


def score_position(
    pos: Position, profile: Profile, now: datetime, sections: list[Section] | None = None
) -> Position:
    sections = _sections(profile, sections)
    title_hits = _match_by_section(pos.title, sections)
    if not is_phd_related(pos.title, pos.description) or not title_hits:
        pos.score = 0.0
        pos.flags.append("标题未命中目标方向")
        return pos

    text = f"{pos.title} {pos.description} {pos.institution} {pos.salary}"
    hits = _match_by_section(text, sections)
    section, keywords = _pick_section(hits, sections)
    if section is None:
        pos.score = 0.0
        return pos

    pos.section = section.key
    pos.keywords = keywords[:10]
    pos.topics = keywords[:10]
    pos.methods = match_terms(text, profile.methods)

    score = min(6.0, 2.0 * len(keywords))
    score += min(2.5, 0.8 * len(pos.methods))
    score += min(3.0, profile.country_bonus.get(pos.country.upper(), 0.0))
    if section.key == "D":
        score = min(score, 4.5)

    if has_funding_signal(f"{pos.description} {pos.salary}"):
        score += 1.5
        pos.flags.append("有薪资/经费线索")
    if has_negative_signal(f"{pos.description} {pos.salary}"):
        score -= 6.0
        pos.flags.append("自费/无资助风险")

    normalized = normalize_keyword_text(text)
    anchor = any(
        keyword_matches(term, normalized)
        for term in ("information systems", "business analytics", "data-driven decision", "digital strategy")
    )
    lowered = normalize(text)
    if any(term.lower() in lowered for term in profile.negative_domains) and not anchor:
        pos.score = 0.0
        pos.flags.append("领域偏离")
        return pos

    if pos.published is not None and pos.published >= now - timedelta(days=7):
        score += 0.5
        pos.flags.append("近 7 天发布")

    pos.score = round(max(0.0, min(10.0, score)), 1)
    return pos


def score_award(
    award: Award, profile: Profile, now: datetime, sections: list[Section] | None = None
) -> Award:
    sections = _sections(profile, sections)
    text = f"{award.title} {award.summary} {award.programme}"
    hits = _match_by_section(text, sections)
    section, keywords = _pick_section(hits, sections)
    if section is None:
        award.score = 0.0
        return award

    award.section = section.key
    award.keywords = keywords[:10]
    award.topics = keywords[:10]

    score = min(7.5, 2.5 * len(keywords))
    score += min(1.0, profile.country_bonus.get(award.country.upper(), 0.0))
    if award.end_year is None or award.end_year >= now.year:
        score += 0.5
    if section.key == "D":
        score = min(score, 5.5)

    normalized = normalize_keyword_text(text)
    anchor = any(
        keyword_matches(term, normalized)
        for term in ("information systems", "business analytics", "data-driven decision", "digital strategy")
    )
    lowered = normalize(text)
    if any(term.lower() in lowered for term in profile.negative_domains) and not anchor:
        award.score = 0.0
        return award

    award.score = round(max(0.0, min(10.0, score)), 1)
    return award


def score_all(
    positions: list[Position],
    awards: list[Award],
    profile: Profile,
    now: datetime,
    sections: list[Section] | None = None,
) -> tuple[list[Position], list[Award]]:
    sections = _sections(profile, sections)
    positions = [score_position(p, profile, now, sections) for p in positions]
    awards = [score_award(a, profile, now, sections) for a in awards]
    positions = [p for p in positions if p.score > 0]
    awards = [a for a in awards if a.score > 0]
    positions.sort(key=lambda p: (-p.score, p.deadline or datetime.max.replace(tzinfo=now.tzinfo)))
    awards.sort(key=lambda a: -a.score)
    return positions, awards
