"""AcademicTransfer（荷兰）岗位源。

官网前端检索接口需要鉴权，但站点 sitemap 暴露了全部在招岗位 URL，
岗位详情页又带 schema.org JobPosting JSON-LD，因此：
1. 读 sitemap 找到 phd/doctoral/promovendus 岗位；
2. 按岗位 ID 倒序取最新的 N 个；
3. 逐个抓详情页 JSON-LD，拿标题、机构、发布/截止日期、地点、描述。
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Position, SourceResult
from ..textutil import strip_html
from ..timeutil import parse_dt
from .base import BaseSource, register

SITEMAP = "https://www.academictransfer.com/sitemap-vacancies.xml"
JOB_URL = re.compile(r"https://www\.academictransfer\.com/(?:en|nl)/jobs/(\d+)/([^<]+?)/?$")
PHD_SLUG = re.compile(r"(phd|doctoral|promovendus)", re.I)


@register
class AcademicTransferSource(BaseSource):
    kind = "academic_transfer"

    def collect(self) -> SourceResult:
        max_details = int(self.options.get("max_details") or 20)
        newest_n = int(self.options.get("newest") or 10)
        domain_n = int(self.options.get("domain") or 10)
        domain_slug = re.compile(
            r"(management|business|econom|financ|organi[sz]ation|information|digital|data|"
            r"innovat|marketing|consumer|analytics|decision|technology|platform|strateg|account|supply|operations)",
            re.I,
        )
        errors: list[str] = []

        try:
            sitemap = self.fetcher.get(SITEMAP).text
        except Exception as exc:  # noqa: BLE001
            return self.failure(f"sitemap: {exc}")

        entries: list[tuple[int, str]] = []
        for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap):
            match = JOB_URL.match(loc)
            if not match:
                continue
            job_id, slug = int(match.group(1)), match.group(2)
            if PHD_SLUG.search(slug) and "postdoc" not in slug:
                entries.append((job_id, loc))
        entries.sort(reverse=True)
        newest = entries[:newest_n]
        domain_hits = [entry for entry in entries if domain_slug.search(entry[1])][:domain_n]
        selected: list[tuple[int, str]] = []
        seen_ids: set[int] = set()
        for entry in newest + domain_hits:
            if entry[0] in seen_ids:
                continue
            seen_ids.add(entry[0])
            selected.append(entry)

        positions: list[Position] = []
        for job_id, url in selected[:max_details]:
            try:
                page = self.fetcher.get(url)
                position = self._parse_detail(job_id, url, page.text)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{job_id}: {exc}")
                continue
            if position is not None:
                positions.append(position)

        if not positions and errors:
            return self.failure("; ".join(errors))
        return self.result(positions=positions, errors=errors)

    def _parse_detail(self, job_id: int, url: str, html: str) -> Position | None:
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", type="application/ld+json")
        if script is None or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None

        job = data.get("mainEntity") if isinstance(data, dict) else None
        if not isinstance(job, dict):
            job = data if isinstance(data, dict) and data.get("@type") == "JobPosting" else None
        if not isinstance(job, dict):
            return None

        title = strip_html(str(job.get("title") or ""))
        if not title:
            return None

        org = job.get("hiringOrganization") or {}
        institution = strip_html(str(org.get("name") or "")) if isinstance(org, dict) else ""

        location = job.get("jobLocation") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address") if isinstance(location, dict) else {}
        city = ""
        country = "NL"
        if isinstance(address, dict):
            city = strip_html(str(address.get("addressLocality") or ""))
            country = strip_html(str(address.get("addressCountry") or "NL")) or "NL"

        description = strip_html(str(job.get("description") or ""))
        salary = job.get("baseSalary")
        salary_text = ""
        if isinstance(salary, dict):
            value = salary.get("value")
            if isinstance(value, dict):
                salary_text = f"{value.get('minValue', '')}–{value.get('maxValue', '')} {salary.get('currency', '')}".strip()
            elif value:
                salary_text = f"{value} {salary.get('currency', '')}".strip()

        return Position(
            id=f"academictransfer:{job_id}",
            title=title,
            institution=institution,
            country=country or "NL",
            city=city,
            url=url,
            source=self.name,
            published=parse_dt(job.get("datePosted")),
            deadline=parse_dt(job.get("validThrough")),
            salary=salary_text,
            description=description[:1500],
        )
