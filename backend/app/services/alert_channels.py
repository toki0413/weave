"""告警出站触达通道（2026-11 gap 审计 G1）

应用内通知只覆盖"家属打开 App"的场景；认知监护的告警价值在发现异常后的
及时触达，家属不打开 App 就永远不知道告警存在。本模块把 warning 及以上
告警推到应用外：

- 邮件：SMTP（stdlib smtplib，零新依赖），按家属的 notify_email 逐人发送
- webhook：企业微信群机器人格式（config-only 接入），全局单地址，适合
  试点期机构/运营侧值守群；对通用 webhook 也兼容（只要求 2xx 响应）

失败隔离原则：任何通道故障只记日志 + Prometheus 计数，绝不影响通知写库
主流程（_create_for_family 的 commit 已先行完成）。短信通道（需要
provider SDK 与签名审核）留待 G2 密钥配置后按同一 dispatch_alert 骨架接入。
"""
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict, List

import httpx
from prometheus_client import Counter
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

logger = logging.getLogger("cognitive_garden")

ALERT_OUTBOUND_TOTAL = Counter(
    "alert_outbound_total",
    "告警出站触达结果（按通道与结果）",
    ["channel", "result"],
)

# severity 出站门槛：info 只留在应用内
_SEVERITY_RANK = {"info": 0, "warning": 1, "danger": 2}

_WEBHOOK_TEXT_MAX = 2000  # 企业微信机器人 text.content 上限


def _send_email(to_addr: str, subject: str, body: str, settings) -> bool:
    """SMTP 发送一封纯文本邮件。配置不全返回 False（视为未启用，不计数）。"""
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        return False
    sender = settings.smtp_from or settings.smtp_user
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("织忆", "utf-8")), sender))
    msg["To"] = to_addr

    if settings.smtp_use_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    try:
        if not settings.smtp_use_ssl:
            try:
                server.starttls()
            except smtplib.SMTPException:
                pass  # 内网中继可能不支持 STARTTLS，明文继续
        with server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(sender, [to_addr], msg.as_string())
    finally:
        try:
            server.close()
        except Exception:
            pass
    return True


def _send_webhook(text: str, webhook_url: str) -> bool:
    """POST 企业微信群机器人格式消息。通用 webhook 只要求 2xx 响应。"""
    payload = {"msgtype": "text", "text": {"content": text[:_WEBHOOK_TEXT_MAX]}}
    resp = httpx.post(webhook_url, json=payload, timeout=10)
    if resp.status_code < 200 or resp.status_code >= 300:
        return False
    # 企业微信机器人用 errcode 表达业务失败（如关键词不匹配），HTTP 仍是 200
    try:
        errcode = resp.json().get("errcode", 0)
    except ValueError:
        return True
    return errcode == 0


def dispatch_alert(
    db: Session,
    family_user_ids: List[str],
    title: str,
    content: str,
    severity: str,
) -> Dict[str, int]:
    """把一条告警推送到应用外通道，返回 {email: 成功人数, webhook: 0/1}。

    severity 低于 alert_outbound_min_severity 的直接跳过（info 不出站）。
    逐通道/逐收件人失败隔离：单人邮件失败不影响其余收件人与 webhook。
    """
    settings = get_settings()
    threshold = _SEVERITY_RANK.get(
        (settings.alert_outbound_min_severity or "warning").lower(), 1)
    if _SEVERITY_RANK.get((severity or "info").lower(), 0) < threshold:
        return {"email": 0, "webhook": 0}

    text = f"【织忆告警·{severity}】{title}\n{content}"
    result = {"email": 0, "webhook": 0}

    # 全局 webhook：试点期机构值守群（企业微信群机器人即插即用）
    if settings.alert_webhook_url:
        try:
            ok = _send_webhook(text, settings.alert_webhook_url)
            ALERT_OUTBOUND_TOTAL.labels(channel="webhook", result="ok" if ok else "fail").inc()
            if ok:
                result["webhook"] = 1
        except Exception:
            ALERT_OUTBOUND_TOTAL.labels(channel="webhook", result="fail").inc()
            logger.warning("webhook 告警触达失败", exc_info=True)

    # 逐家属邮件
    if family_user_ids:
        users = (
            db.query(User)
            .filter(User.id.in_(family_user_ids), User.notify_email.isnot(None))
            .all()
        )
        for u in users:
            try:
                ok = _send_email(
                    u.notify_email, f"【织忆】{title}", text, settings)
                ALERT_OUTBOUND_TOTAL.labels(
                    channel="email", result="ok" if ok else "fail").inc()
                if ok:
                    result["email"] += 1
            except Exception:
                ALERT_OUTBOUND_TOTAL.labels(channel="email", result="fail").inc()
                logger.warning(
                    "邮件告警触达失败 user=%s", u.id, exc_info=True)

    return result
