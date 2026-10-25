"""NWO NWOpen API（荷兰资助项目 / PI）。"""

from __future__ import annotations

from urllib.parse import quote_plus

from ..models import Award, SourceResult
from ..textutil import strip_html
from ..timeutil import now_utc
from .base import BaseSource, register

API = "https://nwopen-api.nwo.nl/NWOpen-API/api/Projects"


@register
class NwoSource(BaseSource):
    kind = "nwo"

    def collect(self) -> SourceResult:
        topics = list(self.options.get("topics") or self.profile.topics or ["information systems"])
        page_size = int(self.options.get("page_size") or 50)
        max_topics = int(self.options.get("max_topics") or 5)
        min_year = now_utc().year - int(self.options.get("years_back") or 3)

        awards: list[Award] = []
        errors: list[str] = []

        for topic in topics[:max_topics]:
            url = f"{API}?summary={quote_plus(topic)}&page=1&pageSize={page_size}"
            try:
                response = self.fetcher.get(url, headers={"Accept": "application/json"})
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{topic}: {exc}")
                continue

            for project in data.get("projects", []):
                start = str(project.get("start_date") or "")
                try:
                    start_year = int(start[:4])
                except ValueError:
                    start_year = None
                if start_year is not None and start_year < min_year:
                    continue

                members = project.get("project_members") or []
                pi = _pick_pi(members)
                institution = ""
                if members:
                    institution = str(members[0].get("organisation") or "")
                summary = strip_html(project.get("summary_en") or project.get("summary_nl") or "")

                awards.append(
                    Award(
                        id=f"nwo:{project.get('project_id')}",
                        title=strip_html(project.get("title") or ""),
                        pi=pi,
                        institution=institution,
                        country="NL",
                        programme=str(project.get("funding_scheme") or "NWO"),
                        url="https://www.nwo.nl/en/projects",
                        source=self.name,
                        start_year=start_year,
                        end_year=_year(project.get("end_date")),
                        summary=summary[:600],
                    )
                )

        awards = _dedupe(awards)
        if not awards and errors:
            return self.failure("; ".join(errors))
        return self.result(awards=awards, errors=errors)


def _pick_pi(members: list[dict]) -> str:
    preferred = ("project leader", "main applicant", "lead applicant", "projectleader")
    for member in members:
        role = str(member.get("role") or "").lower()
        if any(word in role for word in preferred):
            name = " ".join(
                part for part in [member.get("degree_pre_nominal"), member.get("first_name"), member.get("last_name")] if part
            )
            return name.strip()
    return ""


def _year(value: str | None) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _dedupe(awards: list[Award]) -> list[Award]:
    seen: set[str] = set()
    result: list[Award] = []
    for award in awards:
        if award.id in seen:
            continue
        seen.add(award.id)
        result.append(award)
    return result
