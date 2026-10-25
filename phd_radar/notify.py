"""邮件发送：支持 163/QQ SMTP、Resend，多个收件人逐个发送。"""

from __future__ import annotations

import base64
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import requests

from .config import Notify

log = logging.getLogger(__name__)


class NotifyError(RuntimeError):
    pass


@dataclass
class Attachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"


def send_email(
    cfg: Notify, subject: str, text: str, html: str, attachments: list[Attachment] | None = None
) -> str:
    if not cfg.recipients:
        raise NotifyError("未配置收件人：请设置 MAIL_TO（多个邮箱用逗号分隔）或 config.toml 的 [notify].to")
    provider = (cfg.provider or "smtp").lower()
    if provider == "none":
        names = ", ".join(a.filename for a in (attachments or []))
        log.warning("MAIL_PROVIDER=none，仅记录邮件：\n%s\n%s\n附件：%s", subject, text, names or "无")
        return "none"

    sent: list[str] = []
    errors: list[str] = []
    for recipient in cfg.recipients:
        try:
            if provider == "smtp":
                _send_smtp(cfg, recipient, subject, text, html, attachments or [])
            elif provider == "resend":
                _send_resend(cfg, recipient, subject, text, html, attachments or [])
            else:
                raise NotifyError(f"未知邮件通道: {provider}")
            sent.append(recipient)
        except Exception as exc:  # noqa: BLE001
            log.error("发送到 %s 失败: %s", recipient, exc)
            errors.append(f"{recipient}: {exc}")

    if not sent:
        raise NotifyError("; ".join(errors))
    if errors:
        log.warning("部分收件人发送失败: %s", "; ".join(errors))
    return provider


def _build(cfg: Notify, recipient: str, subject: str, text: str, html: str, attachments: list[Attachment]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((cfg.from_name, cfg.from_address))
    message["To"] = recipient
    message["Date"] = formatdate(localtime=True)
    domain = cfg.from_address.split("@")[-1] if "@" in cfg.from_address else "localhost"
    message["Message-ID"] = make_msgid(domain=domain)
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    for attachment in attachments:
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )
    return message


def _send_smtp(
    cfg: Notify, recipient: str, subject: str, text: str, html: str, attachments: list[Attachment]
) -> None:
    if not cfg.username or not cfg.password:
        raise NotifyError("缺少 SMTP 账号或授权码（MAIL_USERNAME / MAIL_PASSWORD）")
    message = _build(cfg, recipient, subject, text, html, attachments)
    try:
        if cfg.smtp_ssl:
            with smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, timeout=45, context=ssl.create_default_context()
            ) as server:
                server.login(cfg.username, cfg.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=45) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(cfg.username, cfg.password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise NotifyError("SMTP 登录失败（535）：检查授权码是否有效、SMTP 服务是否开启") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"SMTP 发送失败：{exc}") from exc


def _send_resend(
    cfg: Notify, recipient: str, subject: str, text: str, html: str, attachments: list[Attachment]
) -> None:
    if not cfg.resend_api_key:
        raise NotifyError("缺少 RESEND_API_KEY")
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {cfg.resend_api_key}", "Content-Type": "application/json"},
        json={
            "from": cfg.resend_from,
            "to": [recipient],
            "subject": subject,
            "text": text,
            "html": html,
            "attachments": [
                {
                    "filename": attachment.filename,
                    "content": base64.b64encode(attachment.content).decode(),
                }
                for attachment in attachments
            ],
        },
        timeout=30,
    )
    if response.status_code >= 300:
        raise NotifyError(f"Resend HTTP {response.status_code}: {response.text[:200]}")
