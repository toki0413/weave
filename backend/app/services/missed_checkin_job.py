# ============ 漏录提醒日任务（W3 · 方案 A） ============
"""进程内 asyncio 日任务，每天北京时刻扫一遍漏录老人并提醒家属。

为什么不引 APScheduler/Celery：本仓库无任何周期任务基建（requirements 里没有，
main.py 里那个 while True 是 SSE 生成器不是调度器），试点是单机部署，
加依赖的收益不抵引入的运维面。多 worker 重复执行用 Redis SETNX 锁挡掉；
Redis 不可用时退化为进程内去重（限流模块同样有这个降级路径）。

幂等有两层：signal_key 含北京日期（同一天重复跑只有一条），Redis 锁
（同日多 worker 只有一个执行）。重启后若已过时刻且当天未跑过，会补跑一次。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings

logger = logging.getLogger("cognitive_garden")

LOCAL_TZ_OFFSET = timedelta(minutes=480)          # 北京
CHECK_INTERVAL_SEC = 300                          # 每 5 分钟看一次是否到点
LOCK_TTL_SEC = 22 * 3600                          # 锁活到次日，跨日自动失效

_task = None
_last_run_date = None                             # 进程内降级去重用


def beijing_now(now_utc=None):
    return (now_utc or datetime.now(timezone.utc)) + LOCAL_TZ_OFFSET


def should_run(now_utc, hour_beijing, last_run_date, today_bj=None):
    """纯时间判定：到了北京时刻且今天还没跑过。单独抽出来是为了可测。"""
    now_bj = beijing_now(now_utc)
    today = today_bj or now_bj.date()
    if now_bj.hour < hour_beijing:
        return False
    return last_run_date != today


def _acquire_daily_lock(today):
    """Redis SETNX 抢当日锁；Redis 不在时退回进程内日期标记。"""
    from app.redis_client import get_redis, is_redis_available
    key = f"missed_checkin:lock:{today}"
    if is_redis_available():
        try:
            return bool(get_redis().set(key, "1", nx=True, ex=LOCK_TTL_SEC))
        except Exception as e:                       # 连接抖动也不炸主流程
            logger.warning("漏录提醒 Redis 锁异常，退回进程内去重: %s", e)
    global _last_run_date
    if _last_run_date == today:
        return False
    _last_run_date = today
    return True


def run_once():
    """执行一次扫描，返回写入的通知条数。"""
    from app.database import SessionLocal
    from app.services.notification_service import create_missed_checkin_notifications
    settings = get_settings()
    db = SessionLocal()
    try:
        n = create_missed_checkin_notifications(db, threshold_days=settings.missed_checkin_threshold_days)
        if n:
            logger.info("漏录提醒：写入 %d 条", n)
        return n
    except Exception as e:
        logger.error("漏录提醒任务失败: %s", e, exc_info=True)
        return 0
    finally:
        db.close()


async def _loop():
    global _last_run_date
    settings = get_settings()
    hour = settings.missed_checkin_hour
    while True:
        try:
            now = datetime.now(timezone.utc)
            today = beijing_now(now).date()
            if should_run(now, hour, _last_run_date) and _acquire_daily_lock(today):
                _last_run_date = today
                await asyncio.get_event_loop().run_in_executor(None, run_once)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("漏录提醒循环异常: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


def start_daily_job():
    """在应用启动时调用；开关关闭或已在跑则不重复启动。"""
    global _task
    settings = get_settings()
    if not settings.missed_checkin_enabled:
        logger.info("漏录提醒已关闭（missed_checkin_enabled=False）")
        return None
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        logger.info("漏录提醒日任务已启动：每天 %02d:00（北京）", settings.missed_checkin_hour)
    return _task
