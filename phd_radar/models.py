"""数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Position:
    id: str
    title: str
    institution: str
    country: str
    url: str
    source: str
    city: str = ""
    published: datetime | None = None
    deadline: datetime | None = None
    salary: str = ""
    description: str = ""
    topics: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    score: float = 0.0
    flags: list[str] = field(default_factory=list)

    def summary(self) -> str:
        bits = [self.institution, self.country, f"截止 {self.deadline:%Y-%m-%d}" if self.deadline else ""]
        return " · ".join(b for b in bits if b)


@dataclass
class Award:
    id: str
    title: str
    pi: str
    institution: str
    country: str
    programme: str
    url: str
    source: str
    start_year: int | None = None
    end_year: int | None = None
    amount: str = ""
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    score: float = 0.0

    def summary_line(self) -> str:
        years = f"{self.start_year or '?'}–{self.end_year or '?'}"
        return " · ".join(b for b in [self.pi, self.institution, self.programme, years] if b)


@dataclass
class SourceResult:
    name: str
    kind: str
    ok: bool
    positions: list[Position] = field(default_factory=list)
    awards: list[Award] = field(default_factory=list)
    error: str = ""
    errors: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.positions) + len(self.awards)


@dataclass
class Batch:
    positions: list[Position] = field(default_factory=list)
    awards: list[Award] = field(default_factory=list)
    sources: list[SourceResult] = field(default_factory=list)

    @property
    def ok_sources(self) -> int:
        return sum(1 for s in self.sources if s.ok)

    def new_positions(self, seen: set[str]) -> list[Position]:
        return [p for p in self.positions if p.id not in seen]

    def new_awards(self, seen: set[str]) -> list[Award]:
        return [a for a in self.awards if a.id not in seen]
