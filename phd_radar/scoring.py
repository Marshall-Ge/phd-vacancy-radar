"""关键词加权打分与板块归类。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Profile, Section, Subsection
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


@dataclass
class SectionMatch:
    section: Section
    score: float
    subsection: str
    keywords: list[str]
    title_hit: bool


def _sections(profile: Profile, sections: list[Section] | None) -> list[Section]:
    if sections:
        return sections
    return [
        Section(
            key="A",
            name="目标方向",
            priority=1,
            anchors=list(profile.topics),
            subsections=[Subsection(name="关键词", weight=2.0, keywords=list(profile.topics))],
        )
    ]


def _match_section(title: str, body: str, section: Section) -> SectionMatch:
    title_norm = normalize_keyword_text(title)
    body_norm = normalize_keyword_text(body)
    score = 0.0
    title_hit = False
    matched: list[str] = []
    best_sub = ""
    best_sub_score = 0.0
    seen: set[str] = set()

    for subsection in section.subsections:
        for keyword in subsection.keywords:
            key = normalize_keyword_text(keyword)
            if not key or key in seen:
                continue
            seen.add(key)
            in_title = keyword_matches(keyword, title_norm)
            in_body = keyword_matches(keyword, body_norm)
            if not in_title and not in_body:
                continue
            weight = subsection.weight * (2.0 if in_title else 1.0)
            score += weight
            title_hit = title_hit or in_title
            matched.append(keyword)
            if weight > best_sub_score:
                best_sub_score = weight
                best_sub = subsection.name

    for anchor in section.anchors:
        key = normalize_keyword_text(anchor)
        if not key or key in seen:
            continue
        seen.add(key)
        in_title = keyword_matches(anchor, title_norm)
        in_body = keyword_matches(anchor, body_norm)
        if not in_title and not in_body:
            continue
        score += 2.0 if in_title else 1.0
        title_hit = title_hit or in_title
        matched.append(anchor)
        if 2.0 > best_sub_score:
            best_sub_score = 2.0
            best_sub = "方向关键词"

    return SectionMatch(
        section=section,
        score=round(score, 2),
        subsection=best_sub,
        keywords=matched[:12],
        title_hit=title_hit,
    )


def _best_match(title: str, body: str, sections: list[Section]) -> SectionMatch | None:
    matches = [_match_section(title, body, section) for section in sections]
    candidates = [m for m in matches if m.title_hit and m.score >= 2.0]
    if not candidates:
        return None
    return max(candidates, key=lambda m: (m.score, -m.section.priority))


def score_position(
    pos: Position, profile: Profile, now: datetime, sections: list[Section] | None = None
) -> Position:
    sections = _sections(profile, sections)
    if not is_phd_related(pos.title, pos.description):
        pos.score = 0.0
        pos.flags.append("非博士岗位")
        return pos

    text = f"{pos.title} {pos.description} {pos.institution} {pos.salary}"
    match = _best_match(pos.title, text, sections)
    if match is None:
        pos.score = 0.0
        pos.flags.append("标题未命中任何板块")
        return pos

    pos.section = match.section.key
    pos.subsection = match.subsection
    pos.keywords = match.keywords
    pos.topics = match.keywords
    pos.methods = match_terms(text, profile.methods)

    score = min(6.0, match.score * 0.8)
    score += min(2.0, 0.8 * len(pos.methods))
    score += min(3.0, profile.country_bonus.get(pos.country.upper(), 0.0))
    if match.section.key == "D":
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
    match = _best_match(award.title, text, sections)
    if match is None:
        award.score = 0.0
        return award

    award.section = match.section.key
    award.subsection = match.subsection
    award.keywords = match.keywords
    award.topics = match.keywords

    score = min(7.5, match.score * 0.9)
    score += min(1.0, profile.country_bonus.get(award.country.upper(), 0.0))
    if award.end_year is None or award.end_year >= now.year:
        score += 0.5
    if match.section.key == "D":
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
