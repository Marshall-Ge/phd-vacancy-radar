"""邮件与附件渲染（按 A/B/C/D 四个板块）。"""

from __future__ import annotations

import csv
import html as html_lib
import io
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from .config import Config, Section
from .models import Award, Position
from .notify import Attachment
from .state import State
from .timeutil import human_cst, human_kst

MANUAL_LINKS = [
    ("EURAXESS", "https://euraxess.ec.europa.eu/jobs/search"),
    ("AcademicTransfer", "https://www.academictransfer.com/en/jobs/"),
    ("jobs.ac.uk", "https://www.jobs.ac.uk/search/?keywords=PhD"),
    ("FindAPhD", "https://www.findaphd.com/"),
    ("LinkedIn Jobs", "https://www.linkedin.com/jobs/"),
    ("ERC 项目库", "https://erc.europa.eu/projects-statistics/funded-projects"),
    ("GEPRIS", "https://gepris.dfg.de/"),
    ("NWO 项目", "https://www.nwo.nl/en/projects"),
    ("UKRI GtR", "https://gtr.ukri.org/"),
]


def _e(value: str) -> str:
    return html_lib.escape(value or "", quote=True)


def _google(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def _sections(cfg: Config) -> list[Section]:
    return cfg.sections or [Section(key="A", name="A｜项目", keywords=[], priority=1)]


def _groups(cfg: Config, positions: list[Position], awards: list[Award]):
    sections = _sections(cfg)
    grouped = {s.key: ([], []) for s in sections}
    for pos in positions:
        key = pos.section if pos.section in grouped else sections[0].key
        grouped[key][0].append(pos)
    for award in awards:
        key = award.section if award.section in grouped else sections[0].key
        grouped[key][1].append(award)
    return [(s, *grouped[s.key]) for s in sections]


def _count_text(positions: list[Position], awards: list[Award]) -> str:
    return f"项目 {len(positions)} 个 · funding {len(awards)} 个"


def render_test(cfg: Config, now: datetime) -> tuple[str, str, str]:
    subject = "[PhD Radar] 邮件通道测试"
    text = "\n".join(
        [
            "这是一封测试邮件。",
            f"收件人：{', '.join(cfg.notify.recipients)}",
            f"发送通道：{cfg.notify.provider}",
            f"发送时间：{human_cst(now)}",
        ]
    )
    html = f"""<!doctype html><html><body style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f4f5f7;padding:24px">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:28px">
<h2 style="margin:0 0 12px">邮件通道测试成功 ✅</h2>
<p style="color:#374151">收到这封邮件说明 PhD Vacancy Radar 的发信配置正常。</p>
<p style="color:#6b7280;font-size:14px">收件人：{_e(', '.join(cfg.notify.recipients))}<br>通道：{_e(cfg.notify.provider)}<br>时间：{_e(human_cst(now))}</p>
</div></body></html>"""
    return subject, text, html


def render_alert(cfg: Config, positions: list[Position], awards: list[Award], now: datetime) -> tuple[str, str, str]:
    subject = f"[PhD Radar] 发现 {len(positions) + len(awards)} 个新项目/funding（项目 {len(positions)} / funding {len(awards)}）"
    text = "\n".join(
        [
            "发现新的项目 / funding",
            "",
            f"项目 {len(positions)} 个，funding {len(awards)} 个。",
            "",
            *_section_text(cfg, positions, awards, detail_limit=3),
            f"检查时间：{human_cst(now)}",
        ]
    )
    html = _wrap(
        cfg,
        title="发现新项目 / funding",
        subtitle=_count_text(positions, awards),
        intro="下面按 A/B/C/D 四个板块整理；点标题即可跳转原始页面。",
        positions=positions,
        awards=awards,
        now=now,
        detail_limit=3,
        footer="本邮件由云端定时任务自动发送；看到合适的项目请尽快申请。",
    )
    return subject, text, html


def render_digest(
    cfg: Config,
    positions: list[Position],
    awards: list[Award],
    state: State,
    now: datetime,
    *,
    startup: bool = False,
) -> tuple[str, str, str]:
    total = len(positions) + len(awards)
    if startup:
        subject = f"[PhD Radar] 监控已启动（基线：{len(positions)} 个项目 / {len(awards)} 个 funding）"
        intro = (
            "监控已经跑起来了。我已经把当前项目和 funding 做了基线记录；"
            "之后只要有新项目，会立刻单独发邮件；每 5 天再发一次汇总。"
        )
    elif total == 0:
        subject = "[PhD Radar] 本期无新增（监控正常）"
        intro = "过去 5 天没有发现新的匹配项目或 funding。监控仍在正常运行。"
    else:
        subject = f"[PhD Radar] 5 天汇总：{len(positions)} 个新项目，{len(awards)} 个新 funding"
        intro = (
            "这是过去 5 天的新增汇总。A/B/C/D 四个板块只列项目；"
            "funding 作为支撑线索放在最后，完整清单见附件。"
        )

    next_at = _next_digest(cfg, now)
    text = "\n".join(
        [
            subject,
            "",
            intro,
            "",
            *_section_text(cfg, positions, awards, detail_limit=cfg.monitor.digest_detail_items),
            *_attachment_text(cfg),
            "手动检索入口：",
            *[f"- {name}: {url}" for name, url in MANUAL_LINKS],
            "",
            f"已连续监控：{_days(state, now)} 天",
            f"本次检查：{human_cst(now)}",
            f"下次汇总：{human_cst(next_at)} 左右",
        ]
    )
    html = _wrap(
        cfg,
        title="5 天汇总" if not startup else "监控已启动",
        subtitle=_count_text(positions, awards),
        intro=intro,
        positions=positions,
        awards=awards,
        now=now,
        detail_limit=cfg.monitor.digest_detail_items,
        footer=f"下次汇总约在 {human_cst(next_at)}。完整清单见附件。",
        show_manual=True,
    )
    return subject, text, html


def render_health(cfg: Config, sources, now: datetime) -> tuple[str, str, str]:
    subject = "[PhD Radar] 监控异常：所有信息源都抓取失败"
    failed = "、".join(s.name for s in sources if not s.ok) or "全部"
    text = "\n".join(
        [
            "监控异常",
            "",
            f"最近一次检查中，以下信息源失败：{failed}",
            "请到 GitHub Actions 查看日志；可能是站点改版、反爬或网络问题。",
            f"检查时间：{human_cst(now)}",
        ]
    )
    html = f"""<!doctype html><html><body style="font-family:-apple-system,'PingFang SC',sans-serif;background:#f4f5f7;padding:24px">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:28px">
<h2 style="margin:0 0 12px;color:#b91c1c">监控异常</h2>
<p style="color:#374151;line-height:1.7">所有信息源都抓取失败了。最近一次检查：{_e(human_cst(now))}</p>
<p style="color:#374151">失败源：{_e(failed)}</p>
<p style="color:#6b7280;font-size:14px">请到 GitHub Actions 查看运行日志，确认是站点改版还是网络问题。</p>
</div></body></html>"""
    return subject, text, html


def _attachment_text(cfg: Config) -> list[str]:
    mode = (cfg.monitor.digest_attachment or "none").lower()
    if mode == "none":
        return []
    label = {"csv": "CSV", "html": "HTML", "both": "CSV + HTML"}.get(mode, mode)
    return [f"完整清单见附件（{label}）。", ""]


def _section_text(
    cfg: Config, positions: list[Position], awards: list[Award], *, detail_limit: int
) -> list[str]:
    lines: list[str] = []
    for section, sec_positions, sec_awards in _groups(cfg, positions, awards):
        lines.append(f"【{section.name}】项目 {len(sec_positions)}")
        if not sec_positions:
            lines.append("- 本期无新项目")
        else:
            for pos in sec_positions[:detail_limit]:
                lines.extend(_pos_text(pos))
            if len(sec_positions) > detail_limit:
                for pos in sec_positions[detail_limit:]:
                    lines.append(f"- {pos.title}｜{pos.institution} · {pos.country}｜{pos.url}")
        if sec_awards:
            lines.append(f"  另有 {len(sec_awards)} 条相关 funding 线索，见下方「支撑线索」/附件。")
        lines.append("")

    if awards:
        lines.append("【支撑线索：funding / PI（不是岗位，供找导师参考）】")
        for award in awards[: cfg.monitor.funding_display_limit]:
            lines.extend(_award_text(award))
        if len(awards) > cfg.monitor.funding_display_limit:
            lines.append(f"- 另有 {len(awards) - cfg.monitor.funding_display_limit} 条 funding 见附件 CSV。")
        lines.append("")
    return lines


def _pos_text(pos: Position) -> list[str]:
    lines = [f"- {pos.title}", f"  {pos.summary()}"]
    if pos.salary:
        lines.append(f"  薪资/经费：{pos.salary[:160]}")
    if pos.keywords:
        lines.append(f"  命中关键词：{'、'.join(pos.keywords[:5])}")
    lines.append(f"  链接：{pos.url}")
    return lines


def _award_text(award: Award) -> list[str]:
    lines = [f"- {award.title}", f"  {award.summary_line()}"]
    if award.keywords:
        lines.append(f"  命中关键词：{'、'.join(award.keywords[:5])}")
    lines.append(f"  详情页：{award.url}")
    if award.pi:
        lines.append(f"  查 PI 招聘：{_google(award.pi + ' PhD position')}")
    return lines


def _wrap(
    cfg: Config,
    *,
    title: str,
    subtitle: str,
    intro: str,
    positions: list[Position],
    awards: list[Award],
    now: datetime,
    detail_limit: int,
    footer: str,
    show_manual: bool = False,
) -> str:
    blocks = []
    for section, sec_positions, sec_awards in _groups(cfg, positions, awards):
        blocks.append(_section_block(section, sec_positions, sec_awards, detail_limit))

    funding = _funding_block(cfg, awards)

    manual = ""
    if show_manual:
        manual = (
            '<div style="margin-top:22px;font-size:13px;font-weight:700">手动检索入口</div>'
            '<div style="margin-top:8px">'
            + "".join(
                f'<a href="{_e(url)}" style="display:inline-block;margin:4px 6px 4px 0;padding:7px 11px;'
                f'background:#111827;color:#fff;text-decoration:none;border-radius:6px;font-size:12px">{_e(name)}</a>'
                for name, url in MANUAL_LINKS
            )
            + "</div>"
        )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title></head>
<body style="margin:0;padding:24px 12px;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">
  <div style="background:#0f172a;padding:22px 26px">
    <div style="color:#94a3b8;font-size:12px;letter-spacing:1px">PhD VACANCY RADAR</div>
    <div style="color:#fff;font-size:24px;font-weight:700;margin-top:6px">{_e(title)}</div>
    <div style="color:#cbd5e1;font-size:13px;margin-top:8px">{_e(subtitle)}</div>
  </div>
  <div style="padding:24px 26px">
    <p style="margin:0 0 10px;color:#374151;font-size:14px;line-height:1.75">{_e(intro)}</p>
    {''.join(blocks)}
    {funding}
    {manual}
    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;line-height:1.7">
      检查时间：{_e(human_cst(now))}（{_e(human_kst(now))}）<br>
      {_e(footer)}
    </div>
  </div>
</div>
</body></html>"""


def _funding_block(cfg: Config, awards: list[Award]) -> str:
    if not awards:
        return ""
    limit = cfg.monitor.funding_display_limit
    cards = "".join(_award_card(a) for a in awards[:limit])
    note = ""
    if len(awards) > limit:
        note = (
            f'<div style="color:#6b7280;font-size:12px;margin-top:8px">'
            f"另有 {len(awards) - limit} 条 funding 见附件 CSV。</div>"
        )
    return (
        '<div style="margin-top:28px;padding-top:18px;border-top:2px solid #e5e7eb">'
        '<div style="font-size:16px;font-weight:700;color:#4c1d95;border-left:4px solid #7c3aed;padding-left:10px">'
        "支撑线索：funding / PI（不是岗位）</div>"
        '<div style="font-size:12px;color:#6b7280;margin:6px 0 4px 14px">'
        "这些是已获 funding 的项目，不是学校发布的岗位；可顺着 PI/机构去找团队招聘页。</div>"
        f"{cards}{note}</div>"
    )


def _section_block(
    section: Section,
    positions: list[Position],
    awards: list[Award],
    detail_limit: int,
) -> str:
    count = f"项目 {len(positions)}"
    if awards:
        count += f" · 另有 funding 线索 {len(awards)} 条"
    if not positions:
        body = '<div style="color:#9ca3af;font-size:13px;padding:6px 0">本期无新项目</div>'
    else:
        body = "".join(_pos_card(p) for p in positions[:detail_limit])
        body += _compact_positions(positions[detail_limit:])
    return (
        '<div style="margin-top:24px">'
        f'<div style="font-size:16px;font-weight:700;color:#111827;border-left:4px solid #2563eb;padding-left:10px">'
        f"{_e(section.name)}</div>"
        f'<div style="font-size:12px;color:#6b7280;margin:4px 0 6px 14px">{_e(count)}</div>'
        f"{body}</div>"
    )


def _pos_card(pos: Position) -> str:
    deadline = f"截止 {pos.deadline:%Y-%m-%d}" if pos.deadline else ""
    salary = pos.salary[:120] if pos.salary else "薪资/经费见原页面"
    keywords = f"命中关键词：{'、'.join(pos.keywords[:5])}" if pos.keywords else ""
    return (
        '<div style="border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:10px 0">'
        f'<div style="font-size:12px;color:#6b7280;margin-bottom:5px">{_e(deadline)}</div>'
        f'<a href="{_e(pos.url)}" style="color:#1d4ed8;text-decoration:none;font-size:15px;font-weight:700;line-height:1.5">{_e(pos.title)}</a>'
        f'<div style="font-size:13px;color:#4b5563;margin-top:5px">{_e(pos.institution)} · {_e(pos.country)}'
        + (f" · {_e(pos.city)}" if pos.city else "")
        + "</div>"
        f'<div style="font-size:12px;color:#6b7280;margin-top:4px">{_e(salary)}</div>'
        + (f'<div style="font-size:12px;color:#065f46;margin-top:6px">{_e(keywords)}</div>' if keywords else "")
        + f'<div style="font-size:12px;color:#374151;margin-top:6px;line-height:1.6">{_e(pos.description[:180])}</div>'
        "</div>"
    )


def _award_card(award: Award) -> str:
    years = f"{award.start_year or '?'}–{award.end_year or '?'}"
    pi_line = f"PI：{award.pi} · " if award.pi else ""
    keywords = f"命中关键词：{'、'.join(award.keywords[:5])}" if award.keywords else ""
    links = ""
    if award.pi:
        links += (
            f'<a href="{_e(_google(award.pi + " PhD position"))}" style="color:#1d4ed8;font-size:12px;'
            'text-decoration:none;margin-right:12px">查 PI 是否招博士 →</a>'
        )
    links += f'<a href="{_e(award.url)}" style="color:#1d4ed8;font-size:12px;text-decoration:none">详情页 →</a>'
    return (
        '<div style="border:1px solid #e5e7eb;border-left:4px solid #7c3aed;border-radius:10px;padding:14px 16px;margin:10px 0">'
        f'<div style="font-size:12px;color:#6b7280;margin-bottom:5px">{_e(award.programme)} · {_e(years)}</div>'
        f'<a href="{_e(award.url)}" style="color:#1d4ed8;text-decoration:none;font-size:15px;font-weight:700;line-height:1.5">{_e(award.title)}</a>'
        f'<div style="font-size:13px;color:#4b5563;margin-top:5px">{_e(pi_line)}{_e(award.institution)} · {_e(award.country)}</div>'
        + (f'<div style="font-size:12px;color:#065f46;margin-top:6px">{_e(keywords)}</div>' if keywords else "")
        + f'<div style="font-size:12px;margin-top:8px">{links}</div>'
        "</div>"
    )


def _compact_positions(positions: list[Position]) -> str:
    if not positions:
        return ""
    rows = "".join(
        '<div style="padding:6px 0;border-bottom:1px dashed #e5e7eb;font-size:12px;line-height:1.6">'
        f'<a href="{_e(pos.url)}" style="color:#1d4ed8;text-decoration:none">{_e(pos.title[:110])}</a>'
        f'<span style="color:#6b7280"> · {_e(pos.institution[:60])} · {_e(pos.country)}</span>'
        "</div>"
        for pos in positions
    )
    return (
        f'<div style="margin:14px 0 6px;font-size:13px;font-weight:700">其余项目（{len(positions)}）</div>'
        f'<div style="border-top:1px solid #e5e7eb">{rows}</div>'
    )


def _compact_awards(awards: list[Award]) -> str:
    if not awards:
        return ""
    rows = "".join(
        '<div style="padding:6px 0;border-bottom:1px dashed #e5e7eb;font-size:12px;line-height:1.6">'
        f'<a href="{_e(award.url)}" style="color:#1d4ed8;text-decoration:none">{_e(award.title[:110])}</a>'
        f'<span style="color:#6b7280"> · {_e(award.pi[:40] or "PI 未列")} · {_e(award.institution[:50])} · {_e(award.country)}</span>'
        "</div>"
        for award in awards
    )
    return (
        f'<div style="margin:14px 0 6px;font-size:13px;font-weight:700">其余 funding（{len(awards)}）</div>'
        f'<div style="border-top:1px solid #e5e7eb">{rows}</div>'
    )


def _next_digest(cfg: Config, now: datetime) -> datetime:
    tz = ZoneInfo(cfg.monitor.timezone)
    local = now.astimezone(tz) + timedelta(days=cfg.monitor.digest_every_days)
    return local.replace(hour=cfg.monitor.digest_hour, minute=0, second=0, microsecond=0)


def _days(state: State, now: datetime) -> int:
    if not state.created_at:
        return 0
    return max(0, int((now - state.created_at).total_seconds() / 86400))


# ---------------------------------------------------------------------------
# 附件：CSV / HTML 完整清单（按四个板块）
# ---------------------------------------------------------------------------
CSV_HEADER = [
    "板块", "类型", "标题", "机构", "国家", "城市", "PI", "来源/计划",
    "截止日期", "发布日期", "薪资/经费", "命中关键词", "链接", "摘要",
]


def _ordered_rows(cfg: Config, positions: list[Position], awards: list[Award]):
    rows = []
    groups = _groups(cfg, positions, awards)
    for section, sec_positions, _ in groups:
        for pos in sec_positions:
            rows.append(("position", section, pos))
    for section, _, sec_awards in groups:
        for award in sec_awards:
            rows.append(("award", section, award))
    return rows


def build_csv(cfg: Config, positions: list[Position], awards: list[Award]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for kind, section, item in _ordered_rows(cfg, positions, awards):
        if kind == "position":
            pos = item
            writer.writerow([
                section.name, "项目", pos.title, pos.institution, pos.country, pos.city, "",
                pos.source, pos.deadline.strftime("%Y-%m-%d") if pos.deadline else "",
                pos.published.strftime("%Y-%m-%d") if pos.published else "", pos.salary,
                " / ".join(pos.keywords), pos.url, (pos.description or "")[:300],
            ])
        else:
            award = item
            writer.writerow([
                section.name, "funding", award.title, award.institution, award.country, "",
                award.pi, award.programme, "", "",
                f"{award.start_year or ''}-{award.end_year or ''}".strip("-"),
                " / ".join(award.keywords), award.url, (award.summary or "")[:300],
            ])
    return buffer.getvalue().encode("utf-8-sig")


def build_full_html(cfg: Config, positions: list[Position], awards: list[Award], now: datetime) -> bytes:
    blocks = []
    groups = _groups(cfg, positions, awards)
    for section, sec_positions, _ in groups:
        rows = []
        for pos in sec_positions:
            rows.append(
                "<tr>"
                f"<td>项目</td><td><a href='{_e(pos.url)}'>{_e(pos.title)}</a></td>"
                f"<td>{_e(pos.institution)}</td><td>{_e(pos.country)}</td>"
                f"<td>{_e(pos.deadline.strftime('%Y-%m-%d') if pos.deadline else '')}</td>"
                f"<td>{_e(pos.salary)}</td><td>{_e(' / '.join(pos.keywords))}</td>"
                "</tr>"
            )
        body = "".join(rows) or '<tr><td colspan="7" style="color:#9ca3af">本期无新项目</td></tr>'
        blocks.append(
            f"<h2>{_e(section.name)} <small style='color:#6b7280'>项目 {len(sec_positions)}</small></h2>"
            "<table><thead><tr><th>类型</th><th>标题</th><th>机构</th><th>国家</th><th>截止</th><th>薪资</th><th>命中关键词</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )

    award_rows = []
    for section, _, sec_awards in groups:
        for award in sec_awards:
            award_rows.append(
                "<tr>"
                f"<td>{_e(section.name)}</td><td><a href='{_e(award.url)}'>{_e(award.title)}</a></td>"
                f"<td>{_e(award.pi)}</td><td>{_e(award.institution)}</td>"
                f"<td>{_e(award.programme)}</td><td>{_e(' / '.join(award.keywords))}</td>"
                "</tr>"
            )
    funding_body = "".join(award_rows) or '<tr><td colspan="6" style="color:#9ca3af">本期无新增</td></tr>'
    blocks.append(
        "<h2>支撑线索：funding / PI（不是岗位）</h2>"
        "<table><thead><tr><th>板块</th><th>项目</th><th>PI</th><th>机构</th><th>计划</th><th>命中关键词</th></tr></thead>"
        f"<tbody>{funding_body}</tbody></table>"
    )

    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>PhD Radar 完整清单 {now:%Y-%m-%d}</title>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;padding:24px;color:#111827}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:26px}} small{{font-weight:400}}
.meta{{color:#6b7280;font-size:12px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}}
th,td{{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f4f6}} a{{color:#1d4ed8;text-decoration:none}}
</style></head><body>
<h1>PhD Radar 完整清单</h1>
<div class="meta">生成时间：{_e(human_cst(now))}｜项目 {len(positions)} 个｜funding {len(awards)} 个</div>
{''.join(blocks)}
</body></html>"""
    return html.encode("utf-8")


def build_attachments(cfg: Config, positions: list[Position], awards: list[Award], now: datetime) -> list[Attachment]:
    mode = (cfg.monitor.digest_attachment or "none").lower()
    if mode not in {"csv", "html", "both"}:
        return []
    stamp = now.astimezone(ZoneInfo(cfg.monitor.timezone)).strftime("%Y-%m-%d")
    attachments: list[Attachment] = []
    if mode in {"csv", "both"}:
        attachments.append(
            Attachment(
                filename=f"phd-radar-{stamp}.csv",
                content=build_csv(cfg, positions, awards),
                maintype="text",
                subtype="csv",
            )
        )
    if mode in {"html", "both"}:
        attachments.append(
            Attachment(
                filename=f"phd-radar-{stamp}.html",
                content=build_full_html(cfg, positions, awards, now),
                maintype="text",
                subtype="html",
            )
        )
    return attachments
