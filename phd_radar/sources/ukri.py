"""UKRI Gateway to Research API（英国资助项目）。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from ..models import Award, SourceResult
from ..textutil import strip_html
from ..timeutil import now_utc
from .base import BaseSource, register

API = "https://gtr.ukri.org/gtr/api/projects"
NS_PROJECT = "http://gtr.rcuk.ac.uk/gtr/api/project"
NS_BASE = "http://gtr.rcuk.ac.uk/gtr/api"
NS_PART = "http://gtr.rcuk.ac.uk/gtr/api/organisation"


@register
class UkriSource(BaseSource):
    kind = "ukri"

    def collect(self) -> SourceResult:
        queries = list(self.options.get("queries") or ["information systems"])
        size = int(self.options.get("size") or 50)
        max_queries = int(self.options.get("max_queries") or 4)
        min_year = now_utc().year - int(self.options.get("years_back") or 3)

        awards: list[Award] = []
        errors: list[str] = []

        for query in queries[:max_queries]:
            url = f"{API}?q={quote_plus(query)}&page=1&size={size}"
            try:
                response = self.fetcher.get(url, headers={"Accept": "application/xml"})
                root = ET.fromstring(response.text)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query}: {exc}")
                continue

            for project in root.findall(f"{{{NS_PROJECT}}}project"):
                start, end = _fund_dates(project)
                if start and start < min_year:
                    continue
                title = strip_html(project.findtext(f"{{{NS_PROJECT}}}title") or "")
                summary = strip_html(project.findtext(f"{{{NS_PROJECT}}}abstractText") or "")
                status = strip_html(project.findtext(f"{{{NS_PROJECT}}}status") or "")
                if status.lower() == "closed":
                    continue
                funder = strip_html(project.findtext(f"{{{NS_PROJECT}}}leadFunder") or "UKRI")
                org = _lead_org(project)
                pid = project.get(f"{{{NS_BASE}}}id") or title

                awards.append(
                    Award(
                        id=f"ukri:{pid}",
                        title=title,
                        pi="",
                        institution=org,
                        country="UK",
                        programme=f"{funder}" + (f" · {status}" if status else ""),
                        url=f"https://gtr.ukri.org/projects?ref={pid}",
                        source=self.name,
                        start_year=start,
                        end_year=end,
                        summary=summary[:600],
                    )
                )

        awards = _dedupe(awards)
        if not awards and errors:
            return self.failure("; ".join(errors))
        return self.result(awards=awards, errors=errors)


def _fund_dates(project) -> tuple[int | None, int | None]:
    for link in project.iter(f"{{{NS_BASE}}}link"):
        if link.get("rel") == "FUND":
            return _year(link.get("start")), _year(link.get("end"))
    return None, None


def _lead_org(project) -> str:
    for participant in project.iter(f"{{{NS_PROJECT}}}participant"):
        role = participant.findtext(f"{{{NS_PROJECT}}}role") or ""
        if role == "LEAD_PARTICIPANT":
            return strip_html(participant.findtext(f"{{{NS_PROJECT}}}organisationName") or "")
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
