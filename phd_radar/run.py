"""主流程：抓取 → 评分 → 立即告警 / 5 天汇总 → 状态。"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config, load_config
from .fetch import Fetcher
from .models import Award, Batch, Position, SourceResult
from .notify import NotifyError, send_email
from .report import build_attachments, render_alert, render_digest, render_health, render_test
from .scoring import score_all
from .sources import build_source
from .state import State, load_state, save_state
from .timeutil import days_since, hours_since, human_cst, now_utc, to_kst

log = logging.getLogger("phd_radar")


def collect(cfg: Config) -> Batch:
    fetcher = Fetcher()
    batch = Batch()
    for source_cfg in cfg.sources:
        if not source_cfg.enabled:
            continue
        try:
            source = build_source(source_cfg, fetcher, cfg.profile)
            result = source.collect()
        except Exception as exc:  # noqa: BLE001
            log.exception("source %s failed", source_cfg.type)
            result = SourceResult(name=source_cfg.name, kind=source_cfg.type, ok=False, error=str(exc))
        batch.sources.append(result)
        batch.positions.extend(result.positions)
        batch.awards.extend(result.awards)
        log.info(
            "source=%s ok=%s positions=%d awards=%d%s",
            result.name,
            result.ok,
            len(result.positions),
            len(result.awards),
            "" if result.ok else f" error={result.error[:160]}",
        )
    return batch


def _digest_due(cfg: Config, state: State, now: datetime) -> bool:
    if state.last_digest_at is None:
        return True
    if days_since(state.last_digest_at, now) < cfg.monitor.digest_every_days:
        return False
    local = now.astimezone(ZoneInfo(cfg.monitor.timezone))
    return local.hour >= cfg.monitor.digest_hour


def _active(pos: Position, now: datetime) -> bool:
    return pos.deadline is None or pos.deadline >= now - timedelta(days=1)


def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    now = now_utc()

    if args.mode == "status":
        return _print_status(cfg)
    if args.mode == "test-email":
        subject, text, html = render_test(cfg, now)
        if args.dry_run:
            print(subject)
            print(text)
            return 0
        try:
            provider = send_email(cfg.notify, subject, text, html)
        except NotifyError as exc:
            log.error("测试邮件失败: %s", exc)
            return 1
        print(f"✅ 测试邮件已通过 {provider} 发送到 {', '.join(cfg.notify.recipients)}")
        return 0

    state, is_new = load_state(cfg.state_path)
    if is_new:
        state.created_at = now

    log.info("run mode=%s dry_run=%s new_state=%s", args.mode, args.dry_run, is_new)
    batch = collect(cfg)
    positions, awards = score_all(batch.positions, batch.awards, cfg.profile, now)
    positions = [p for p in positions if _active(p, now)]
    awards = [a for a in awards if a.end_year is None or a.end_year >= now.year - 1]

    log.info(
        "scored positions=%d awards=%d ok_sources=%d",
        len(positions),
        len(awards),
        batch.ok_sources,
    )

    if batch.ok_sources == 0 and batch.sources:
        last_health = state.last_alert("health")
        stale = state.last_success_at is None or hours_since(state.last_success_at, now) >= cfg.monitor.failure_alert_after_hours
        cooldown = last_health is None or hours_since(last_health, now) >= cfg.monitor.failure_alert_cooldown_hours
        if stale and cooldown:
            subject, text, html = render_health(cfg, batch.sources, now)
            if args.dry_run:
                print(subject)
                return 0
            try:
                send_email(cfg.notify, subject, text, html)
            except NotifyError as exc:
                log.error("健康告警失败: %s", exc)
                return 1
            state.mark_alert("health", now)
            _save(cfg, state, now, force=True, persist=not args.dry_run)
            return 0
        log.warning("所有信息源失败，尚未到告警阈值")
        _save(cfg, state, now, force=False, persist=not args.dry_run)
        return 0

    state.last_success_at = now

    new_positions = [p for p in positions if p.id not in state.seen_positions]
    new_awards = [a for a in awards if a.id not in state.seen_awards]

    for pos in new_positions:
        state.remember("position", pos.id, now)
    for award in new_awards:
        state.remember("award", award.id, now)

    state.stats["runs"] = state.stats.get("runs", 0) + 1

    # 首次运行：建立基线，不发逐条告警
    if is_new or not state.first_run_done:
        state.first_run_done = True
        if cfg.monitor.startup_email:
            top_positions = [p for p in positions if p.score > 0][: cfg.monitor.max_items_per_email]
            top_awards = [a for a in awards if a.score > 0][: cfg.monitor.max_items_per_email]
            subject, text, html = render_digest(cfg, top_positions, top_awards, state, now, startup=True)
            if args.dry_run:
                _preview(subject, text)
            else:
                try:
                    send_email(
                        cfg.notify,
                        subject,
                        text,
                        html,
                        attachments=build_attachments(cfg, top_positions, top_awards, now),
                    )
                except NotifyError as exc:
                    log.error("启动邮件失败: %s", exc)
                    return 1
                log.info("startup digest sent")
        state.last_digest_at = now
        _save(cfg, state, now, force=True, persist=not args.dry_run)
        return 0

    # 立即告警：新岗位/新资助达到阈值
    alert_positions = [p for p in new_positions if p.score >= cfg.monitor.alert_score][: cfg.monitor.max_items_per_email]
    alert_awards = [a for a in new_awards if a.score >= cfg.monitor.award_alert_score][: cfg.monitor.max_items_per_email]

    digest_due = _digest_due(cfg, state, now) or args.mode == "digest"

    sent_alert = False
    if alert_positions or alert_awards:
        subject, text, html = render_alert(cfg, alert_positions, alert_awards, now)
        if args.dry_run:
            _preview(subject, text)
        else:
            try:
                send_email(cfg.notify, subject, text, html)
            except NotifyError as exc:
                log.error("告警邮件失败: %s", exc)
                return 1
            log.info("alert sent: %d positions, %d awards", len(alert_positions), len(alert_awards))
        for item in alert_positions + alert_awards:
            state.alerted[item.id] = now.isoformat()
        state.mark_alert("new_items", now)
        sent_alert = True

    if digest_due and not sent_alert:
        since = state.last_digest_at or (now - timedelta(days=cfg.monitor.digest_every_days))
        # 5 天汇总尽量全：包含这段时间所有首次发现的项（含已即时提醒过的），
        # 不再因为「已提醒」而排除；上限只用于防止极端刷屏。
        digest_positions = [
            p for p in positions if (state.first_seen("position", p.id) or now) >= since
        ][: cfg.monitor.digest_max_items]
        digest_awards = [
            a for a in awards if (state.first_seen("award", a.id) or now) >= since
        ][: cfg.monitor.digest_max_items]

        subject, text, html = render_digest(cfg, digest_positions, digest_awards, state, now)
        if args.dry_run:
            _preview(subject, text)
        else:
            try:
                send_email(
                    cfg.notify,
                    subject,
                    text,
                    html,
                    attachments=build_attachments(cfg, digest_positions, digest_awards, now),
                )
            except NotifyError as exc:
                log.error("汇总邮件失败: %s", exc)
                return 1
            log.info("digest sent: %d positions, %d awards", len(digest_positions), len(digest_awards))
        state.last_digest_at = now
        state.stats["digests"] = state.stats.get("digests", 0) + 1

    if not (alert_positions or alert_awards or digest_due):
        log.info("no email needed (no new high-score items, digest not due)")

    state.last_snapshot = {
        "positions": len(positions),
        "awards": len(awards),
        "top_positions": [p.title for p in positions[:5]],
        "top_awards": [a.title for a in awards[:5]],
        "checked_at": now.isoformat(),
    }
    _save(cfg, state, now, force=sent_alert or digest_due, persist=not args.dry_run)
    return 0


def _save(cfg: Config, state: State, now: datetime, *, force: bool, persist: bool) -> None:
    checkpoint = state.last_check_at is None or hours_since(state.last_check_at, now) >= 6
    state.last_check_at = now
    if not persist:
        return
    if force or checkpoint:
        save_state(cfg.state_path, state)
        log.info("state saved -> %s", cfg.state_path)


def _preview(subject: str, text: str) -> None:
    print("=" * 72)
    print("Subject:", subject)
    print("-" * 72)
    print(text)
    print("=" * 72)


def _print_status(cfg: Config) -> int:
    state, is_new = load_state(cfg.state_path)
    print(f"目标画像: {cfg.profile.name}")
    print(f"收件人: {', '.join(cfg.notify.recipients) or '(未配置)'}")
    print(f"信息源: {[s.name for s in cfg.sources if s.enabled]}")
    if is_new:
        print("状态：尚未运行")
        return 0
    print(f"已监控: {max(0, int(days_since(state.created_at)))} 天")
    print(f"上次检查: {human_cst(state.last_check_at)}")
    print(f"上次成功: {human_cst(state.last_success_at)}")
    print(f"上次汇总: {human_cst(state.last_digest_at)}")
    print(f"已见岗位: {len(state.seen_positions)}，已见资助: {len(state.seen_awards)}")
    print(f"累计: {state.stats.get('runs', 0)} 次检查 / {state.stats.get('alerts', 0)} 次告警")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phd-radar", description="岗位制 PhD / 资助项目雷达")
    parser.add_argument(
        "mode",
        nargs="?",
        default="check",
        choices=["check", "digest", "test-email", "status"],
        help="check=检查并发送；digest=强制 5 天汇总；test-email=测试邮件；status=查看状态",
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception:  # noqa: BLE001
        log.exception("运行失败")
        return 1
