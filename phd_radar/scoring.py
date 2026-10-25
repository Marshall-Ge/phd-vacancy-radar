"""匹配评分。"""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import Profile
from .models import Award, Position
from .textutil import (
    has_funding_signal,
    has_negative_signal,
    is_phd_related,
    match_terms,
    match_topics,
    normalize,
)


def score_position(pos: Position, profile: Profile, now: datetime) -> Position:
    # 标题是硬门槛：标题里没有任何目标主题，直接丢弃。
    # 否则「工程/生物/医学」岗位只要正文出现 management 就会被误收。
    title_topics = match_topics(pos.title, profile.topics)
    if not is_phd_related(pos.title, pos.description) or not title_topics:
        pos.topics = title_topics
        pos.score = 0.0
        pos.flags.append("标题未命中目标主题")
        return pos

    text = f"{pos.title} {pos.description} {pos.institution} {pos.salary}"
    desc_topics = [t for t in match_topics(text, profile.topics) if t not in title_topics]
    pos.topics = title_topics + desc_topics
    pos.methods = match_terms(text, profile.methods)
    core = [t for t in title_topics if t in profile.core_topics]

    score = min(6.0, 2.0 * len(core))
    score += min(2.0, 0.5 * len(desc_topics))
    score += min(2.5, 0.8 * len(pos.methods))
    score += min(3.0, profile.country_bonus.get(pos.country.upper(), 0.0))

    if has_funding_signal(f"{pos.description} {pos.salary}"):
        score += 1.5
        pos.flags.append("有资助/薪资线索")
    if has_negative_signal(f"{pos.description} {pos.salary}"):
        score -= 6.0
        pos.flags.append("自费/无资助风险")

    lowered = normalize(text)
    anchor = any(
        t in title_topics
        for t in ("information systems", "business analytics", "data-driven decision", "digital strategy")
    )
    if any(term.lower() in lowered for term in profile.negative_domains) and not anchor:
        score -= 5.0
        pos.flags.append("领域偏离")

    if pos.published is not None and pos.published >= now - timedelta(days=7):
        score += 0.5
        pos.flags.append("近 7 天发布")

    pos.score = round(max(0.0, min(10.0, score)), 1)
    return pos


def score_award(award: Award, profile: Profile, now: datetime | None = None) -> Award:
    now = now or datetime.now()
    text = f"{award.title} {award.summary} {award.programme}"
    award.topics = match_topics(text, profile.topics)
    core = [t for t in award.topics if t in profile.core_topics]
    if not core:
        award.score = 0.0
        return award

    score = min(7.5, 2.5 * len(core))
    score += min(1.0, 0.5 * (len(award.topics) - len(core)))
    score += min(1.0, profile.country_bonus.get(award.country.upper(), 0.0))
    if award.end_year is None or award.end_year >= now.year:
        score += 0.5

    lowered = normalize(text)
    anchor = any(
        t in award.topics
        for t in ("information systems", "business analytics", "data-driven decision", "digital strategy")
    )
    if any(term.lower() in lowered for term in profile.negative_domains) and not anchor:
        score -= 5.0
    award.score = round(max(0.0, min(10.0, score)), 1)
    return award


def score_all(
    positions: list[Position], awards: list[Award], profile: Profile, now: datetime
) -> tuple[list[Position], list[Award]]:
    positions = [score_position(p, profile, now) for p in positions]
    awards = [score_award(a, profile, now) for a in awards]
    positions = [p for p in positions if p.score > 0]
    awards = [a for a in awards if a.score > 0]
    positions.sort(key=lambda p: (-p.score, p.deadline or datetime.max.replace(tzinfo=now.tzinfo)))
    awards.sort(key=lambda a: -a.score)
    return positions, awards
