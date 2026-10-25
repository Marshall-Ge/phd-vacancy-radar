"""配置加载。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Subsection:
    name: str
    weight: float
    keywords: list[str] = field(default_factory=list)


@dataclass
class Section:
    key: str
    name: str
    priority: int = 99
    anchors: list[str] = field(default_factory=list)
    subsections: list[Subsection] = field(default_factory=list)


@dataclass
class Profile:
    name: str = "信息系统 / 管理 / 数据驱动决策"
    topics: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    core_topics: list[str] = field(default_factory=list)
    domain_terms: list[str] = field(default_factory=list)
    negative_domains: list[str] = field(default_factory=list)
    country_bonus: dict[str, float] = field(default_factory=dict)


@dataclass
class Monitor:
    digest_every_days: int = 5
    digest_hour: int = 9
    timezone: str = "Asia/Shanghai"
    alert_score: float = 6.5
    award_alert_score: float = 7.0
    max_items_per_email: int = 10
    digest_max_items: int = 150
    digest_detail_items: int = 8
    digest_attachment: str = "csv"  # csv | html | both | none
    funding_per_section_limit: int = 3
    funding_display_limit: int = 10
    startup_email: bool = True
    state_file: str = "state.json"
    failure_alert_after_hours: int = 12
    failure_alert_cooldown_hours: int = 24


@dataclass
class Notify:
    provider: str = "smtp"
    recipients: list[str] = field(default_factory=list)
    from_name: str = "PhD Vacancy Radar"
    username: str = ""
    password: str = ""
    smtp_host: str = "smtp.163.com"
    smtp_port: int = 465
    smtp_ssl: bool = True
    resend_from: str = "onboarding@resend.dev"
    resend_api_key: str = ""

    @property
    def from_address(self) -> str:
        return self.username or (self.recipients[0] if self.recipients else "")


@dataclass
class SourceConfig:
    type: str
    name: str
    enabled: bool = True
    options: dict = field(default_factory=dict)


@dataclass
class Config:
    profile: Profile
    monitor: Monitor
    notify: Notify
    sources: list[SourceConfig]
    base_dir: Path
    state_path: Path
    sections: list[Section] = field(default_factory=list)


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    value = value.strip() if isinstance(value, str) else ""
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_emails(value: str | list | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = []
        for item in value:
            parts.extend(str(item).replace(";", ",").split(","))
    return [p.strip() for p in parts if p.strip()]


def load_config(path: str | Path = "config.toml") -> Config:
    path = Path(path)
    raw: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            raw = tomllib.load(fh)

    profile_raw = raw.get("profile", {})
    monitor_raw = raw.get("monitor", {})
    notify_raw = raw.get("notify", {})

    profile = Profile(
        name=profile_raw.get("name", Profile.name),
        topics=[str(x) for x in profile_raw.get("topics", [])],
        methods=[str(x) for x in profile_raw.get("methods", [])],
        negative=[str(x) for x in profile_raw.get("negative", [])],
        core_topics=[str(x) for x in profile_raw.get("core_topics", [])],
        domain_terms=[str(x) for x in profile_raw.get("domain_terms", [])],
        negative_domains=[str(x) for x in profile_raw.get("negative_domains", [])],
        country_bonus={str(k): float(v) for k, v in (profile_raw.get("country_bonus") or {}).items()},
    )

    monitor = Monitor(
        digest_every_days=int(monitor_raw.get("digest_every_days", 5)),
        digest_hour=int(monitor_raw.get("digest_hour", 9)),
        timezone=str(monitor_raw.get("timezone", "Asia/Shanghai")),
        alert_score=float(monitor_raw.get("alert_score", 6.5)),
        award_alert_score=float(monitor_raw.get("award_alert_score", 7.0)),
        max_items_per_email=int(monitor_raw.get("max_items_per_email", 10)),
        digest_max_items=int(monitor_raw.get("digest_max_items", 150)),
        digest_detail_items=int(monitor_raw.get("digest_detail_items", 8)),
        digest_attachment=str(monitor_raw.get("digest_attachment", "csv")).lower(),
        funding_per_section_limit=int(monitor_raw.get("funding_per_section_limit", 3)),
        funding_display_limit=int(monitor_raw.get("funding_display_limit", 10)),
        startup_email=bool(monitor_raw.get("startup_email", True)),
        state_file=str(monitor_raw.get("state_file", "state.json")),
        failure_alert_after_hours=int(monitor_raw.get("failure_alert_after_hours", 12)),
        failure_alert_cooldown_hours=int(monitor_raw.get("failure_alert_cooldown_hours", 24)),
    )

    env_recipients = _split_emails(os.environ.get("MAIL_TO"))
    recipients = env_recipients or _split_emails(notify_raw.get("to"))

    notify = Notify(
        provider=_env("MAIL_PROVIDER", str(notify_raw.get("provider", "smtp"))).lower(),
        recipients=recipients,
        from_name=_env("MAIL_FROM_NAME", str(notify_raw.get("from_name", Notify.from_name))),
        username=_env("MAIL_USERNAME", str(notify_raw.get("username", ""))),
        password=_env("MAIL_PASSWORD", str(notify_raw.get("password", ""))),
        smtp_host=_env("SMTP_HOST", str(notify_raw.get("smtp_host", "smtp.163.com"))),
        smtp_port=int(_env("SMTP_PORT", str(notify_raw.get("smtp_port", 465)))),
        smtp_ssl=_env_bool("SMTP_SSL", bool(notify_raw.get("smtp_ssl", True))),
        resend_from=_env("RESEND_FROM", str(notify_raw.get("resend_from", "onboarding@resend.dev"))),
        resend_api_key=_env("RESEND_API_KEY", str(notify_raw.get("resend_api_key", ""))),
    )

    sources: list[SourceConfig] = []
    for entry in raw.get("source", []):
        if not isinstance(entry, dict) or "type" not in entry:
            continue
        options = {k: v for k, v in entry.items() if k not in {"type", "name", "enabled"}}
        sources.append(
            SourceConfig(
                type=str(entry["type"]),
                name=str(entry.get("name") or entry["type"]),
                enabled=bool(entry.get("enabled", True)),
                options=options,
            )
        )

    sections: list[Section] = []
    for entry in raw.get("section", []):
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        subs: list[Subsection] = []
        for sub in entry.get("sub", []):
            if not isinstance(sub, dict):
                continue
            subs.append(
                Subsection(
                    name=str(sub.get("name") or "关键词"),
                    weight=float(sub.get("weight", 2.0)),
                    keywords=[str(x) for x in sub.get("keywords", [])],
                )
            )
        if not subs and entry.get("keywords"):
            subs = [Subsection(name="关键词", weight=2.0, keywords=[str(x) for x in entry["keywords"]])]
        anchors = [str(x) for x in entry.get("anchors", [])] or [kw for sub in subs for kw in sub.keywords]
        sections.append(
            Section(
                key=str(entry["key"]),
                name=str(entry.get("name") or entry["key"]),
                priority=int(entry.get("priority", 99)),
                anchors=anchors,
                subsections=subs,
            )
        )
    if not sections:
        sections = [
            Section(
                key="A",
                name="目标方向",
                priority=1,
                anchors=list(profile.topics),
                subsections=[Subsection(name="关键词", weight=2.0, keywords=list(profile.topics))],
            ),
        ]

    base_dir = path.resolve().parent
    state_path = Path(_env("STATE_FILE", monitor.state_file))
    if not state_path.is_absolute():
        state_path = base_dir / state_path

    return Config(
        profile=profile,
        monitor=monitor,
        notify=notify,
        sources=sources,
        sections=sections,
        base_dir=base_dir,
        state_path=state_path,
    )
