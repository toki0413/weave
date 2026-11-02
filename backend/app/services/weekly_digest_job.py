# ============ 家属周摘要周任务（gap G5） ============
"""进程内 asyncio 周任务，每周固定日（默认周一上午，北京）给绑定家属写一条周摘要。

调度骨架与 missed_checkin_job 同款：不引 APScheduler（试点单机，加依赖的
收益不抵运维面），多 worker 重复执行用 Redis SETNX 周锁挡掉；Redis 不可用
退进程内周标记去重。

幂等有三重：周锁（同周多 worker 只有一个执行）、signal_key 含周起始日
（notification_service 对 weekly_digest 的 6 天冷却，同周重复跑只有一条）、
重启补跑后仍然幂等。内容只聚合本周会话计数/活跃天数/情绪天数，不暴露
叙事原文与分数；本周零记录不发——那是 missed_checkin 的职责，不双通道打扰。
"""
import asyncio
import logging
import time
from datetime import datetime, time as dtime, timedelta, timezone

from app.config import get_settings
from prometheus_client import Gauge

logger = logging.getLogger("cognitive_garden")

LOCAL_TZ = timezone(timedelta(minutes=480))       # 北京
CHECK_INTERVAL_SEC = 300                          # 每 5 分钟看一次是否到点
LOCK_TTL_SEC = 8 * 24 * 3600                      # 周锁活到下周，跨周自动失效

WEEKLY_DIGEST_LAST_SUCCESS = Gauge(
    "weekly_digest_last_success_timestamp",
    "周摘要任务最近一次成功执行的 Unix 时间戳",
)

_task = None
_last_week_key = None                             # 进程内降级去重用


def beijing_now(now_utc=None):
    return (now_utc or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)


def week_key_bj(now_utc=None):
    """本周（北京）周起始日的 ISO 字符串，周一为一周之始"""
    d = beijing_now(now_utc).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def should_run_week(now_utc, weekday, hour, last_week_key, week_key=None):
    """纯时间判定：到了 configured 星期几的 configured 时刻且本周还没跑过"""
    now_bj = beijing_now(now_utc)
    if now_bj.weekday() != weekday:
        return False
    if now_bj.hour < hour:
        return False
    return (week_key or week_key_bj(now_utc)) != last_week_key


def _acquire_week_lock(week_key):
    """Redis SETNX 抢本周锁；Redis 不在时退回进程内周标记"""
    from app.redis_client import get_redis, is_redis_available
    key = f"weekly_digest:lock:{week_key}"
    if is_redis_available():
        try:
            return bool(get_redis().set(key, "1", nx=True, ex=LOCK_TTL_SEC))
        except Exception as e:
            logger.warning("周摘要 Redis 锁异常，退回进程内去重: %s", e)
    global _last_week_key
    if _last_week_key == week_key:
        return False
    _last_week_key = week_key
    return True


def collect_weekly_stats(db, elderly_user_id: str, week_start):
    """聚合本周（北京周一起）脱敏统计；无任何记录返回 None"""
    from app.models import Session as DBSession
    since_utc = datetime.combine(week_start, dtime.min, tzinfo=LOCAL_TZ) \
        .astimezone(timezone.utc)
    sessions = (
        db.query(DBSession.created_at, DBSession.emotion_label)
        .filter(DBSession.user_id == elderly_user_id,
                DBSession.created_at >= since_utc)
        .all()
    )
    if not sessions:
        return None
    record_count = len(sessions)
    active_days = len({
        (s[0] or since_utc).astimezone(LOCAL_TZ).date() for s in sessions
    })
    negative_days = len({
        (s[0] or since_utc).astimezone(LOCAL_TZ).date()
        for s in sessions if s[1] == "negative"
    })
    return {
        "record_count": record_count,
        "active_days": active_days,
        "negative_days": negative_days,
    }


def create_weekly_digest_notifications(db, week_start=None) -> int:
    """给所有绑定家属写本周摘要，返回写入条数"""
    from app.models import FamilyLink
    from app.services.notification_service import _create_for_family
    week_start = week_start or beijing_now().date() - timedelta(
        days=beijing_now().date().weekday())
    rows = db.query(FamilyLink.elderly_user_id).filter(
        FamilyLink.is_active == True).distinct().all()      # noqa: E712
    written = 0
    for (elderly_id,) in rows:
        stats = collect_weekly_stats(db, elderly_id, week_start)
        if stats is None:
            continue  # 本周零记录：漏录提醒已覆盖，不双通道打扰
        if stats["negative_days"] >= 3:
            mood_line = f"本周有 {stats['negative_days']} 天情绪偏低，找时间陪 TA 聊聊天。"
        else:
            mood_line = "状态平稳，继续陪伴就好。"
        title = "本周记忆摘要"
        content = (
            f"本周 TA 记录了 {stats['record_count']} 次回忆，"
            f"覆盖 {stats['active_days']} 天。{mood_line}"
        )
        written += _create_for_family(
            db, elderly_id, "weekly_digest", title, content, "info",
            related_data={"week_start": week_start.isoformat(), **stats},
            signal_key=f"weekly_digest|{week_start.isoformat()}",
        )
    return written


def run_once() -> int:
    """执行一次周扫描，返回写入的通知条数"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        n = create_weekly_digest_notifications(db)
        if n:
            logger.info("周摘要：写入 %d 条", n)
        WEEKLY_DIGEST_LAST_SUCCESS.set(time.time())
        return n
    except Exception as e:
        logger.error("周摘要任务失败: %s", e, exc_info=True)
        return 0
    finally:
        db.close()


async def _loop():
    global _last_week_key
    settings = get_settings()
    while True:
        try:
            now = datetime.now(timezone.utc)
            week_key = week_key_bj(now)
            if (should_run_week(now, settings.weekly_digest_weekday,
                                settings.weekly_digest_hour, _last_week_key,
                                week_key)
                    and _acquire_week_lock(week_key)):
                _last_week_key = week_key
                await asyncio.get_event_loop().run_in_executor(None, run_once)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("周摘要循环异常: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


def start_weekly_job():
    """在应用启动时调用；开关关闭或已在跑则不重复启动"""
    global _task
    settings = get_settings()
    if not settings.weekly_digest_enabled:
        logger.info("家属周摘要已关闭（weekly_digest_enabled=False）")
        return None
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        logger.info("家属周摘要周任务已启动：每周%s %02d:00（北京）",
                    "一二三四五六日"[settings.weekly_digest_weekday],
                    settings.weekly_digest_hour)
    return _task
