"""DFG GEPRIS 项目检索（德国资助项目 / PI）。

使用 GEPRIS 网页前端自身的检索接口（POST /backend/project/search）。
只取「当前在研」项目（static_status=EIN），并按主题查询。
"""

from __future__ import annotations

import time

from ..models import Award, SourceResult
from ..textutil import strip_html
from ..timeutil import now_utc
from .base import BaseSource, register

SEARCH_URL = "https://gepris.dfg.de/backend/project/search"


@register
class GeprisSource(BaseSource):
    kind = "gepris"

    def collect(self) -> SourceResult:
        queries = list(self.options.get("queries") or ["information systems"])
        size = int(self.options.get("size") or 50)
        max_queries = int(self.options.get("max_queries") or 5)
        min_year = now_utc().year - int(self.options.get("years_back") or 2)

        awards: list[Award] = []
        errors: list[str] = []

        for index, query in enumerate(queries[:max_queries]):
            if index:
                time.sleep(1.0)
            body = {"query_string": query, "static_status": ["EIN"], "size": size, "from": 0}
            try:
                response = self.fetcher.post_json(
                    SEARCH_URL,
                    body,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://gepris.dfg.de",
                        "Referer": "https://gepris.dfg.de/",
                    },
                )
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query}: {exc}")
                continue

            for hit in (data.get("hits") or {}).get("hits", []):
                end_year = _year(hit.get("prj_ende_jahr"))
                if end_year is not None and end_year < min_year:
                    continue
                programme = strip_html(hit.get("prj_verfahren_en") or hit.get("prj_verfahren") or "")
                if any(x in programme.lower() for x in ("publication", "library", "museum")):
                    continue
                awards.append(
                    Award(
                        id=f"gepris:{hit.get('prj_id')}",
                        title=strip_html(hit.get("prj_titel_en") or hit.get("prj_titel") or ""),
                        pi=_pick_pi(hit.get("bt_pers") or []),
                        institution=_institution(hit.get("bt_ins_json") or []),
                        country="DE",
                        programme=strip_html(hit.get("prj_verfahren_en") or hit.get("prj_verfahren") or "DFG"),
                        url=f"https://gepris.dfg.de/gepris/projekt/{hit.get('prj_id')}",
                        source=self.name,
                        start_year=_year(hit.get("prj_beginn_jahr")),
                        end_year=end_year,
                        summary=strip_html(
                            hit.get("prj_ababstract_en")
                            or hit.get("prj_abstract_en")
                            or hit.get("prj_ababstract")
                            or hit.get("prj_abstract")
                            or ""
                        )[:600],
                    )
                )

        awards = _dedupe(awards)
        if not awards and errors:
            return self.failure("; ".join(errors))
        return self.result(awards=awards, errors=errors)


def _pick_pi(people: list[dict]) -> str:
    preferred = ("antragsteller", "projektleitung", "sprecher")
    chosen: list[str] = []
    for person in people:
        role = str(person.get("BTR_BEZEICHNUNG_GRUP") or "").lower()
        name = strip_html(str(person.get("bt_partner_name_komplett") or ""))
        if not name:
            continue
        if any(word in role for word in preferred) or not chosen:
            if name not in chosen:
                chosen.append(name)
        if len(chosen) >= 2:
            break
    return " / ".join(chosen)


def _institution(institutions: list[dict]) -> str:
    for inst in institutions:
        name = strip_html(str(inst.get("ins_namedeutsch") or inst.get("ins_nameenglish") or ""))
        if name:
            return name
    return ""


def _year(value) -> int | None:
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
