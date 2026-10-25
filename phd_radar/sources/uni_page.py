"""通用大学招聘页信息源（用于 UCPH 等没有 API 的学校）。"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Position, SourceResult
from ..textutil import parse_loose_date, strip_html
from .base import BaseSource, register


@register
class UniPageSource(BaseSource):
    kind = "uni_page"

    def collect(self) -> SourceResult:
        url = str(self.options.get("url") or "")
        institution = str(self.options.get("institution") or "")
        country = str(self.options.get("country") or "")
        href_contains = str(self.options.get("href_contains") or "")
        keywords = [str(k).lower() for k in (self.options.get("keywords") or ["phd", "doctoral", "doktorand"])]

        if not url:
            return self.failure("未配置 url")

        try:
            page = self.fetcher.get(url)
        except Exception as exc:  # noqa: BLE001
            return self.failure(exc)

        soup = BeautifulSoup(page.text, "lxml")
        positions: list[Position] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            if href_contains and href_contains not in href:
                continue
            title = strip_html(anchor.get_text(" ", strip=True))
            lowered = title.lower()
            if not title or "postdoc" in lowered:
                continue
            if not any(keyword in lowered for keyword in keywords):
                continue
            if len(title) < 12 or len(title) > 220:
                continue

            absolute = urljoin(url, href)
            if absolute in seen:
                continue
            seen.add(absolute)

            block = anchor
            for _ in range(3):
                if block.parent is None:
                    break
                block = block.parent
                if len(strip_html(block.get_text(" ", strip=True))) > 80:
                    break
            context = strip_html(block.get_text(" ", strip=True))

            positions.append(
                Position(
                    id=f"{self.name}:{absolute}",
                    title=title,
                    institution=institution,
                    country=country,
                    url=absolute,
                    source=self.name,
                    published=None,
                    deadline=_deadline(context),
                    description=context[:500],
                )
            )

        return self.result(positions=positions)


def _deadline(text: str):
    match = re.search(r"(?:deadline|apply before|closing date)[:\s]+([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|\d{1,2}\s+[A-Za-z]{3}\s*\d{0,4})", text, re.I)
    return parse_loose_date(match.group(1)) if match else None
