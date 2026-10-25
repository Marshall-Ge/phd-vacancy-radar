"""邮件内容渲染。"""

from __future__ import annotations

import csv
import html as html_lib
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

from .config import Config
from .models import Award, Position
from .notify import Attachment
from .state import State
from .timeutil import human_cst, human_date, human_kst

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


def _score_color(score: float) -> str:
    if score >= 8:
        return "#c0392b"
    if score >= 6.5:
        return "#b9770e"
    return "#4b5563"


def _why(pos: Position) -> str:
    bits = []
    if pos.topics:
        bits.append("主题：" + "、".join(pos.topics[:4]))
    if pos.methods:
        bits.append("方法：" + "、".join(pos.methods[:3]))
    if pos.flags:
        bits.append("；".join(pos.flags[:3]))
    return " ｜ ".join(bits) if bits else "关键词命中较少，建议人工判断"


def _award_why(award: Award) -> str:
    if award.topics:
        return "主题命中：" + "、".join(award.topics[:5])
    return "与关键词弱相关，建议人工判断"


def _google(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def _pos_text(pos: Position) -> list[str]:
    lines = [
        f"- [{pos.score}] {pos.title}",
        f"  {pos.summary()}",
    ]
    if pos.salary:
        lines.append(f"  薪资/经费：{pos.salary[:160]}")
    lines.append(f"  匹配：{_why(pos)}")
    lines.append(f"  链接：{pos.url}")
    return lines


def _award_text(award: Award) -> list[str]:
    lines = [
        f"- [{award.score}] {award.title}",
        f"  {award.summary_line()}",
        f"  匹配：{_award_why(award)}",
        f"  详情页：{award.url}",
    ]
    if award.pi:
        lines.append(f"  查 PI 招聘：{_google(award.pi + ' PhD position')}")
    return lines


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
    text_lines = ["发现新的高匹配项目 / funding", ""]
    if positions:
        text_lines.append(f"项目（{len(positions)}）")
        for pos in positions:
            text_lines.extend(_pos_text(pos))
        text_lines.append("")
    if awards:
        text_lines.append(f"funding / PI（{len(awards)}）")
        for award in awards:
            text_lines.extend(_award_text(award))
        text_lines.append("")
    text_lines.append(f"检查时间：{human_cst(now)}")

    html = _wrap(
        title="发现新项目 / funding",
        subtitle=f"项目 {len(positions)} 个 · funding / PI {len(awards)} 个",
        intro="下面这些是刚刚发现、且与你的方向匹配度较高的项目 / funding。项目建议尽快点开确认截止日期；funding 可以顺着 PI 去找团队主页和招聘页。",
        positions=positions,
        awards=awards,
        state=None,
        now=now,
        footer="本邮件由云端定时任务自动发送；看到合适的项目请尽快申请。",
        detail_limit=len(positions) + len(awards) + 1,
    )
    return subject, "\n".join(text_lines), html


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
            "监控已经跑起来了。我已经把当前项目和 funding 项目做了基线记录；"
            "之后只要有新项目，会立刻单独发邮件；每 5 天再发一次汇总。"
        )
    elif total == 0:
        subject = "[PhD Radar] 本期无新增（监控正常）"
        intro = "过去 5 天没有发现新的匹配项目或 funding。监控仍在正常运行。"
    else:
        subject = f"[PhD Radar] 5 天汇总：{len(positions)} 个新项目，{len(awards)} 个新 funding"
        intro = (
            f"这是过去 5 天的新增汇总：项目 {len(positions)} 个（{_country_breakdown(positions)}），"
            f"funding {len(awards)} 个（{_country_breakdown(awards)}）。"
            "前几条用详细卡片，其余用紧凑清单，点标题即可跳转。"
        )

    detail = cfg.monitor.digest_detail_items
    text_lines = [subject, "", intro, ""]
    if positions:
        text_lines.append(f"新项目（{len(positions)}）")
        for pos in positions[:detail]:
            text_lines.extend(_pos_text(pos))
        if len(positions) > detail:
            text_lines.append(f"其余 {len(positions) - detail} 个项目（紧凑列表）：")
            for pos in positions[detail:]:
                text_lines.append(f"- [{pos.score}] {pos.title}｜{pos.institution} · {pos.country}｜{pos.url}")
        text_lines.append("")
    if awards:
        text_lines.append(f"新 funding / PI（{len(awards)}）")
        for award in awards[:detail]:
            text_lines.extend(_award_text(award))
        if len(awards) > detail:
            text_lines.append(f"其余 {len(awards) - detail} 个 funding（紧凑列表）：")
            for award in awards[detail:]:
                text_lines.append(
                    f"- [{award.score}] {award.title}｜{award.pi or 'PI 未列'} · {award.institution} · {award.country}｜{award.url}"
                )
        text_lines.append("")
    if not total:
        text_lines.append("- 本期没有新增，稍后继续检查。")
        text_lines.append("")

    next_at = _next_digest(cfg, now)
    attachment_mode = cfg.monitor.digest_attachment
    if attachment_mode in {"csv", "html", "both"}:
        label = {"csv": "CSV", "html": "HTML", "both": "CSV + HTML"}.get(attachment_mode, attachment_mode)
        text_lines.extend(["", f"完整清单见附件（{label}）。"])

    text_lines.extend(
        [
            "手动检索入口：",
            *[f"- {name}: {url}" for name, url in MANUAL_LINKS],
            "",
            f"已连续监控：{_days(state, now)} 天",
            f"本次检查：{human_cst(now)}",
            f"下次汇总：{human_cst(next_at)} 左右",
        ]
    )

    html = _wrap(
        title="5 天汇总" if not startup else "监控已启动",
        subtitle=f"{len(positions)} 个新项目 · {len(awards)} 个新 funding",
        intro=intro,
        positions=positions,
        awards=awards,
        state=state,
        now=now,
        footer=f"下次汇总约在 {human_cst(next_at)}。手动入口见下方。",
        show_manual=True,
        detail_limit=detail,
    )
    return subject, "\n".join(text_lines), html


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


def _next_digest(cfg: Config, now: datetime) -> datetime:
    tz = ZoneInfo(cfg.monitor.timezone)
    local = now.astimezone(tz) + timedelta(days=cfg.monitor.digest_every_days)
    return local.replace(hour=cfg.monitor.digest_hour, minute=0, second=0, microsecond=0)


def _country_breakdown(items) -> str:
    from collections import Counter

    counts = Counter((item.country or "?") for item in items)
    if not counts:
        return "无"
    return " / ".join(f"{code} {count}" for code, count in counts.most_common())


def _days(state: State, now: datetime) -> int:
    if not state.created_at:
        return 0
    return max(0, int((now - state.created_at).total_seconds() / 86400))


def _wrap(
    *,
    title: str,
    subtitle: str,
    intro: str,
    positions: list[Position],
    awards: list[Award],
    state: State | None,
    now: datetime,
    footer: str,
    show_manual: bool = False,
    detail_limit: int = 8,
) -> str:
    pos_cards = "".join(_pos_card(p) for p in positions[:detail_limit])
    award_cards = "".join(_award_card(a) for a in awards[:detail_limit])
    pos_compact = _compact_positions(positions[detail_limit:])
    award_compact = _compact_awards(awards[detail_limit:])
    if not positions and not awards:
        pos_cards = '<p style="color:#6b7280;font-size:14px">本期没有新增项目。</p>'

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
    <p style="margin:0 0 16px;color:#374151;font-size:14px;line-height:1.75">{_e(intro)}</p>
    {pos_cards}
    {pos_compact}
    {award_cards}
    {award_compact}
    {manual}
    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;line-height:1.7">
      检查时间：{_e(human_cst(now))}（{_e(human_kst(now))}）<br>
      {_e(footer)}
    </div>
  </div>
</div>
</body></html>"""


def _compact_positions(positions: list[Position]) -> str:
    if not positions:
        return ""
    rows = "".join(
        '<div style="padding:6px 0;border-bottom:1px dashed #e5e7eb;font-size:12px;line-height:1.6">'
        f'<span style="color:#6b7280">[{pos.score}]</span> '
        f'<a href="{_e(pos.url)}" style="color:#1d4ed8;text-decoration:none">{_e(pos.title[:110])}</a>'
        f'<span style="color:#6b7280"> · {_e(pos.institution[:60])} · {_e(pos.country)}</span>'
        "</div>"
        for pos in positions
    )
    return (
        f'<div style="margin:18px 0 6px;font-size:13px;font-weight:700">其余新增项目（{len(positions)}）</div>'
        f'<div style="border-top:1px solid #e5e7eb">{rows}</div>'
    )


def _compact_awards(awards: list[Award]) -> str:
    if not awards:
        return ""
    rows = "".join(
        '<div style="padding:6px 0;border-bottom:1px dashed #e5e7eb;font-size:12px;line-height:1.6">'
        f'<span style="color:#6b7280">[{award.score}]</span> '
        f'<a href="{_e(award.url)}" style="color:#1d4ed8;text-decoration:none">{_e(award.title[:110])}</a>'
        f'<span style="color:#6b7280"> · {_e(award.pi[:40] or "PI 未列")} · {_e(award.institution[:50])} · {_e(award.country)}</span>'
        "</div>"
        for award in awards
    )
    return (
        f'<div style="margin:18px 0 6px;font-size:13px;font-weight:700">其余新 funding（{len(awards)}）</div>'
        f'<div style="border-top:1px solid #e5e7eb">{rows}</div>'
    )


def _pos_card(pos: Position) -> str:
    color = _score_color(pos.score)
    deadline = f"截止 {pos.deadline:%Y-%m-%d}" if pos.deadline else ""
    salary = pos.salary[:120] if pos.salary else "薪资/经费见原页面"
    return (
        '<div style="border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0">'
        f'<div style="font-size:12px;color:{color};font-weight:700;margin-bottom:5px">匹配 {pos.score}/10 · {_e(deadline)}</div>'
        f'<a href="{_e(pos.url)}" style="color:#1d4ed8;text-decoration:none;font-size:15px;font-weight:700;line-height:1.5">{_e(pos.title)}</a>'
        f'<div style="font-size:13px;color:#4b5563;margin-top:5px">{_e(pos.institution)} · {_e(pos.country)}'
        + (f" · {_e(pos.city)}" if pos.city else "")
        + "</div>"
        f'<div style="font-size:12px;color:#6b7280;margin-top:4px">{_e(salary)}</div>'
        f'<div style="font-size:12px;color:#065f46;margin-top:6px;line-height:1.6">{_e(_why(pos))}</div>'
        f'<div style="font-size:12px;color:#374151;margin-top:6px;line-height:1.6">{_e(pos.description[:180])}</div>'
        "</div>"
    )


def _award_card(award: Award) -> str:
    color = _score_color(award.score)
    years = f"{award.start_year or '?'}–{award.end_year or '?'}"
    pi_line = f"PI：{award.pi} · " if award.pi else ""
    links = ""
    if award.pi:
        links += (
            f'<a href="{_e(_google(award.pi + " PhD position"))}" style="color:#1d4ed8;font-size:12px;'
            'text-decoration:none;margin-right:12px">查 PI 是否招博士 →</a>'
        )
    links += (
        f'<a href="{_e(award.url)}" style="color:#1d4ed8;font-size:12px;text-decoration:none">详情页 →</a>'
    )
    return (
        '<div style="border:1px solid #e5e7eb;border-left:4px solid #7c3aed;border-radius:10px;padding:14px 16px;margin:12px 0">'
        f'<div style="font-size:12px;color:{color};font-weight:700;margin-bottom:5px">匹配 {award.score}/10 · {_e(award.programme)} · {_e(years)}</div>'
        f'<a href="{_e(award.url)}" style="color:#1d4ed8;text-decoration:none;font-size:15px;font-weight:700;line-height:1.5">{_e(award.title)}</a>'
        f'<div style="font-size:13px;color:#4b5563;margin-top:5px">{_e(pi_line)}{_e(award.institution)} · {_e(award.country)}</div>'
        f'<div style="font-size:12px;color:#065f46;margin-top:6px">{_e(_award_why(award))}</div>'
        f'<div style="font-size:12px;margin-top:8px">{links}</div>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# 汇总附件：CSV / HTML 完整清单
# ---------------------------------------------------------------------------
CSV_HEADER = [
    "类型", "匹配分", "标题", "机构", "国家", "城市", "PI", "来源/计划",
    "截止日期", "发布日期", "薪资/经费", "主题", "方法", "链接", "摘要",
]


def build_csv(positions: list[Position], awards: list[Award]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for pos in positions:
        writer.writerow([
            "项目", pos.score, pos.title, pos.institution, pos.country, pos.city, "",
            pos.source, pos.deadline.strftime("%Y-%m-%d") if pos.deadline else "",
            pos.published.strftime("%Y-%m-%d") if pos.published else "", pos.salary,
            " / ".join(pos.topics), " / ".join(pos.methods), pos.url,
            (pos.description or "")[:300],
        ])
    for award in awards:
        writer.writerow([
            "funding", award.score, award.title, award.institution, award.country, "",
            award.pi, award.programme, "", "",
            f"{award.start_year or ''}-{award.end_year or ''}".strip("-"),
            " / ".join(award.topics), "", award.url, (award.summary or "")[:300],
        ])
    return buffer.getvalue().encode("utf-8-sig")


def build_full_html(positions: list[Position], awards: list[Award], now: datetime) -> bytes:
    rows = []
    for pos in positions:
        rows.append(
            "<tr>"
            f"<td>项目</td><td>{pos.score}</td>"
            f'<td><a href="{_e(pos.url)}">{_e(pos.title)}</a></td>'
            f"<td>{_e(pos.institution)}</td><td>{_e(pos.country)}</td>"
            f"<td>{_e(pos.deadline.strftime('%Y-%m-%d') if pos.deadline else '')}</td>"
            f"<td>{_e(pos.salary)}</td><td>{_e(' / '.join(pos.topics))}</td>"
            "</tr>"
        )
    for award in awards:
        rows.append(
            "<tr>"
            f"<td>funding</td><td>{award.score}</td>"
            f'<td><a href="{_e(award.url)}">{_e(award.title)}</a></td>'
            f"<td>{_e(award.institution)}</td><td>{_e(award.country)}</td>"
            f"<td>{_e(award.pi)}</td><td>{_e(award.programme)}</td>"
            f"<td>{_e(' / '.join(award.topics))}</td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="8">本期无新增</td></tr>'
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>PhD Radar 完整清单 {now:%Y-%m-%d}</title>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;padding:24px;color:#111827}}
h1{{font-size:20px}} .meta{{color:#6b7280;font-size:12px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f4f6}} a{{color:#1d4ed8;text-decoration:none}}
</style></head><body>
<h1>PhD Radar 完整清单</h1>
<div class="meta">生成时间：{_e(human_cst(now))}｜项目 {len(positions)} 个｜funding {len(awards)} 个</div>
<table><thead><tr>
<th>类型</th><th>分数</th><th>标题</th><th>机构</th><th>国家</th><th>截止/PI</th><th>薪资/经费</th><th>主题</th>
</tr></thead><tbody>{body}</tbody></table>
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
                content=build_csv(positions, awards),
                maintype="text",
                subtype="csv",
            )
        )
    if mode in {"html", "both"}:
        attachments.append(
            Attachment(
                filename=f"phd-radar-{stamp}.html",
                content=build_full_html(positions, awards, now),
                maintype="text",
                subtype="html",
            )
        )
    return attachments
