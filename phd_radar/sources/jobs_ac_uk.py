"""jobs.ac.uk 搜索信息源（英国）。"""

from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..models import Position, SourceResult
from ..textutil import infer_country, is_phd_related, parse_loose_date, strip_html
from .base import BaseSource, register


@register
class JobsAcUkSource(BaseSource):
    kind = "jobs_ac_uk"

    def collect(self) -> SourceResult:
        queries = list(self.options.get("queries") or [])
        max_pages = int(self.options.get("pages") or 1)
        positions: list[Position] = []
        errors: list[str] = []

        for query in queries:
            for page in range(1, max_pages + 1):
                url = f"https://www.jobs.ac.uk/search/?keywords={quote_plus(query)}&page={page}"
                try:
                    response = self.fetcher.get(url)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{query} p{page}: {exc}")
                    continue
                positions.extend(self._parse(response.text))
        positions = _dedupe(positions)
        if not positions and errors:
            return self.failure("; ".join(errors))
        return self.result(positions=positions, errors=errors)

    def _parse(self, html: str) -> list[Position]:
        soup = BeautifulSoup(html, "lxml")
        results: list[Position] = []
        for card in soup.select("div.j-search-result__result"):
            link = card.select_one("a[href^='/job/']")
            if link is None:
                continue
            title = strip_html(link.get_text(" ", strip=True))
            href = link.get("href", "").split("?")[0]
            text = strip_html(card.get_text(" ", strip=True))
            if not title or not is_phd_related(title, text):
                continue

            employer_node = card.select_one(".j-search-result__employer")
            department_node = card.select_one(".j-search-result__department")
            employer = strip_html(employer_node.get_text(" ", strip=True)) if employer_node else ""
            department = strip_html(department_node.get_text(" ", strip=True)) if department_node else ""

            location = ""
            for div in card.find_all("div"):
                value = strip_html(div.get_text(" ", strip=True))
                if value.startswith("Location:"):
                    location = value.split("Location:", 1)[1].strip()
                    break

            salary_node = card.select_one(".j-search-result__info")
            salary = strip_html(salary_node.get_text(" ", strip=True)) if salary_node else ""

            placed = ""
            for div in card.find_all("div"):
                value = strip_html(div.get_text(" ", strip=True))
                if value.startswith("Date Placed:"):
                    placed = value.split("Date Placed:", 1)[1].strip()
                    break

            deadline = ""
            deadline_node = card.select_one(".j-search-result__date--blue")
            if deadline_node:
                deadline = strip_html(deadline_node.get_text(" ", strip=True))

            results.append(
                Position(
                    id=f"jobsacuk:{href}",
                    title=title,
                    institution=employer or department,
                    country=infer_country(f"{employer} {location} {title} {text}", "UK"),
                    city=location,
                    url=f"https://www.jobs.ac.uk{href}",
                    source=self.name,
                    published=parse_loose_date(placed),
                    deadline=parse_loose_date(deadline),
                    salary=salary,
                    description=text,
                )
            )
        return results


def _dedupe(positions: list[Position]) -> list[Position]:
    seen: set[str] = set()
    result: list[Position] = []
    for pos in positions:
        if pos.id in seen:
            continue
        seen.add(pos.id)
        result.append(pos)
    return result
