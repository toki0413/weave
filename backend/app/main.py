from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import re
import sys
import logging
import time
import asyncio
import json
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.routers import auth, session, graph, baseline, stt, state_sync, backup, scale, lexicon, decline, notification, voice_message, family_sync, share, training, llm, websocket, sync, metrics, memory_card
from app.config import get_settings
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

settings = get_settings()

# Prometheus 指标
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Number of active connections')

# 日志配置：控制台 + 文件轮转（5MB × 3 份）
# 支持 CG_LOG_DIR 环境变量覆盖默认目录，便于沙箱/CI 环境重定向到可写路径
log_dir = Path(os.environ.get("CG_LOG_DIR") or (Path.home() / ".cognitive-garden" / "logs"))
try:
    log_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    log_dir = Path(os.environ.get("TEMP") or ".") / "weave-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
log_level = logging.DEBUG if settings.debug else logging.INFO

root_logger = logging.getLogger()
root_logger.setLevel(log_level)
# 控制台
console_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(console_fmt)
console_handler.setLevel(log_level)
root_logger.addHandler(console_handler)
# 文件轮转：frozen 模式下文件描述符可能被 uvicorn 接管，stream 失效时重开
class SafeRotatingFileHandler(RotatingFileHandler):
    def emit(self, record):
        try:
            if self.stream is None:
                self.stream = self._open()
            super().emit(record)
        except (OSError, ValueError):
            try:
                self.stream = self._open()
                super().emit(record)
            except Exception:
                self.handleError(record)

file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
try:
    file_handler = SafeRotatingFileHandler(
        log_dir / "app.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(file_fmt)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)
except OSError:
    pass

logger = logging.getLogger("cognitive_garden")
logger.info("日志系统启动，日志目录: %s", log_dir)

# 数据库迁移：启动时自动执行 alembic upgrade head
def _get_db_path() -> Path:
    """从 database_url 解析 SQLite 文件路径"""
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        return Path(url.replace("sqlite:///./", "")).resolve()
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "")).resolve()
    return Path.home() / ".cognitive-garden" / "cognitive_garden.db"


def _backup_db_before_migration():
    """迁移前自动备份数据库，仅保留最近3个备份（仅 SQLite 文件库）。

    PostgreSQL 部署由 compose 的 pg-backup 服务负责备份，此处不复制数据文件。
    """
    if not settings.database_url.startswith("sqlite"):
        return
    db_path = _get_db_path()
    if not db_path.exists():
        return
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}.backup.{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info("数据库已备份到: %s", backup_path)

    # 清理旧备份，只保留最近3个
    backups = sorted(backup_dir.glob(f"{db_path.stem}.backup.*{db_path.suffix}"))
    for old in backups[:-3]:
        try:
            old.unlink()
            logger.info("清理旧备份: %s", old)
        except OSError:
            pass


# 多实例并发启动时的迁移互斥键（PostgreSQL 会话级 advisory lock）
_MIGRATION_LOCK_ID = 817263540


def _run_migrations():
    """执行数据库迁移。

    生产语义：迁移失败必须终止启动——静默 create_all 会让实例带着与
    迁移历史不一致的 schema 对外服务（后续迁移再次失败、数据错位）。
    仅当显式设置 allow_create_all_fallback（或 CG_ALLOW_CREATE_ALL=1），
    即开发环境，才允许降级。
    """
    auto_migrate = os.environ.get("CG_AUTO_MIGRATE", "1") == "1"
    if not auto_migrate:
        logger.info("CG_AUTO_MIGRATE=0，跳过 alembic 自动迁移")
        if settings.allow_create_all_fallback:
            Base.metadata.create_all(bind=engine)
        return

    _backup_db_before_migration()

    try:
        from alembic.config import Config
        from alembic import command
        # 打包后从 _MEIPASS 找 alembic；开发时从 backend 目录找
        if hasattr(sys, '_MEIPASS'):
            _alembic_base = Path(sys._MEIPASS)
        else:
            _alembic_base = Path(__file__).parent.parent
        alembic_cfg = Config(str(_alembic_base / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_alembic_base / "alembic"))

        if settings.database_url.startswith("sqlite"):
            command.upgrade(alembic_cfg, "head")
        else:
            # 多 worker / 多副本同时启动时，只允许一个实例执行迁移
            with engine.connect() as lock_conn:
                lock_conn.execute(
                    text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_ID})
                try:
                    command.upgrade(alembic_cfg, "head")
                finally:
                    lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK_ID})
        logger.info("数据库迁移完成")
    except Exception as e:
        if settings.allow_create_all_fallback:
            logger.warning("alembic 迁移失败，按配置降级到 create_all: %s", e)
            logger.warning("如需跳过自动迁移，可设置环境变量 CG_AUTO_MIGRATE=0")
            Base.metadata.create_all(bind=engine)
        else:
            logger.critical(
                "alembic 迁移失败，拒绝以不一致的 schema 启动: %s", e, exc_info=True)
            raise

_run_migrations()

# 初始化 Redis（限流、SSE Pub/Sub、token 黑名单共享）
from app.redis_client import init_redis
init_redis()

# 初始化 KMS（主密钥包装/解包）
from app.services.kms import init_kms
init_kms()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭钩子（替代已弃用的 @app.on_event）

    启动：漏录日课提醒 + 家属周摘要，两个进程内日/周任务，均可用开关停用。
    关闭：取消任务并等待退出。旧实现只启动不停止，进程退出或热重载时
    任务残留在事件循环里，asyncio 会打印 "Task was destroyed but it is
    pending"，测试中反复进出应用也会累积。
    """
    from app.services.missed_checkin_job import start_daily_job, stop_daily_job
    from app.services.weekly_digest_job import start_weekly_job, stop_weekly_job

    start_daily_job()
    start_weekly_job()
    try:
        yield
    finally:
        await stop_weekly_job()
        await stop_daily_job()


app = FastAPI(
    title="Weave API",
    description="Weave · 织忆 - 认知辅助工具后端",
    version="2.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# 漏录日课提醒与家属周摘要的启动/停止已收拢到 lifespan（见文件上方），
# 单机试点够用，不引 APScheduler/Celery。多 worker 由 Redis SETNX 锁去重，
# Redis 不可用时退化到进程内日期标记；关掉开关即可完全停用。

# 请求日志中间件：为每个请求生成 request_id，异常日志与错误响应共用同一标识
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import uuid as _uuid
    request_id = request.headers.get("x-request-id") or _uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "[%s] %s %s 未处理异常", request_id, request.method, request.url.path)
        raise
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "[%s] %s %s %d - %.2fms",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response


_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DIGITS_RE = re.compile(r"/\d+")


def _route_label(request: Request) -> str:
    """Prometheus 端点标签：低基数路由标识。

    主应用可直接取到路由模板；挂载子应用（/api/v1）的匹配发生在 Mount
    内部，外层 scope 没有 route，此时按路径归一化回退——把 UUID、纯数字段
    与超长段替换为占位符，避免 /sessions/{id} 这类路径造成标签基数爆炸。
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None) if route is not None else None
    if path:
        # 挂载子应用的 route.path 不含挂载前缀，用 root_path 补全
        root = request.scope.get("root_path") or ""
        if root and not path.startswith(root):
            return root + path
        return path
    raw = _UUID_RE.sub("{id}", request.url.path)
    raw = _DIGITS_RE.sub("/{n}", raw)
    parts = []
    for seg in raw.split("/"):
        parts.append("{x}" if len(seg) > 24 else seg)
    return ("/".join(parts))[:120] or "/"


# Prometheus 指标中间件
# 注意：call_next 抛异常时也必须归还 ACTIVE_CONNECTIONS 并记录耗时，
# 否则 Gauge 单调增长、错误请求不被计数。
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    ACTIVE_CONNECTIONS.inc()
    start = time.time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        REQUEST_LATENCY.observe(time.time() - start)
        REQUEST_COUNT.labels(
            method=request.method, endpoint=_route_label(request), status=status_code).inc()
        ACTIVE_CONNECTIONS.dec()

# 全局异常处理：生产环境不暴露内部堆栈与服务器文件路径，
# 只返回 request_id，运维凭该标识在日志中定位。
def _internal_error_response(request: Request, exc: Exception, scope: str = ""):
    request_id = getattr(request.state, "request_id", "-")
    logger.error("[%s] %s未处理异常: %s", request_id, scope, exc, exc_info=True)
    if settings.debug:
        detail = str(exc)
    else:
        detail = f"服务出现内部错误，请稍后重试（错误标识 {request_id}）"
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "request_id": request_id},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return _internal_error_response(request, exc)

# CORS：桌面/移动 WebView 默认来源 + 部署方显式白名单（CG_CORS_ORIGINS）。
# 同源反代部署（nginx 同时服务前端与 API）无需额外配置。
_cors_origins = [
    "tauri://localhost",
    "https://tauri.localhost",
]
if settings.cors_origins:
    _cors_origins.extend(
        o.strip() for o in settings.cors_origins.split(",") if o.strip())
if settings.debug:
    _cors_origins.extend([
        "http://localhost:5173",   # Vite 默认开发服务器
        "http://127.0.0.1:5173",
        "http://localhost:1420",   # Tauri dev server（如显式指定）
        "http://127.0.0.1:1420",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # 显式列举，避免通配符与 credentials 组合放大放行面
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

import re
from fastapi.responses import RedirectResponse

# API 路由（v1 版本）
v1_app = FastAPI()

v1_app.include_router(auth.router)
v1_app.include_router(session.router)
v1_app.include_router(graph.router)
v1_app.include_router(baseline.router)
v1_app.include_router(stt.router)
v1_app.include_router(state_sync.router)
v1_app.include_router(backup.router)
v1_app.include_router(scale.router)
v1_app.include_router(lexicon.router)
v1_app.include_router(decline.router)
v1_app.include_router(notification.router)
v1_app.include_router(voice_message.router)
v1_app.include_router(family_sync.router)
v1_app.include_router(share.router)
v1_app.include_router(training.router)
v1_app.include_router(metrics.router)
v1_app.include_router(memory_card.router)
v1_app.include_router(llm.router)
v1_app.include_router(websocket.router)
v1_app.include_router(sync.router)

# 为 v1_app 也添加全局异常处理，确保挂载后的路由也能捕获异常
@v1_app.exception_handler(Exception)
async def v1_global_exception_handler(request: Request, exc: Exception):
    return _internal_error_response(request, exc, scope="v1 ")

app.mount("/api/v1", v1_app)

@app.get("/api")
def api_redirect():
    return RedirectResponse(url="/api/v1")

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """存活/就绪探针：数据库连通 + 数据盘余量。

    只暴露布尔结果，不返回数据库版本、路径等内部信息。
    """
    version = "2.1.0"
    db_connected = False
    disk_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
    except Exception as e:
        logger.warning("健康检查：数据库不可用: %s", e)
    try:
        # 检查实际写入盘（上传目录所在卷），而非 SQLite 路径推演
        probe = Path(os.environ.get("CG_DATA_DIR") or _uploads_dir())
        probe.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(probe)
        disk_ok = disk.free > 100 * 1024 * 1024  # 100MB
    except Exception as e:
        logger.warning("健康检查：数据盘不可用: %s", e)
    return {
        "status": "ok" if db_connected and disk_ok else "degraded",
        "version": version,
        "db_connected": db_connected,
        "disk_ok": disk_ok,
    }

# SSE 实时通知（鉴权：EventSource 无法自定义请求头，凭证经 query 传递）
from app.services.events import add_event_queue, remove_event_queue

_SSE_HEARTBEAT_SEC = 15


def _verify_sse_token(token: str) -> bool:
    """校验 SSE 查询参数中的 access token（签名、类型、黑名单、用户存在）。"""
    if not token:
        return False
    try:
        import jwt as _jwt
        from app.redis_client import is_token_blacklisted
        payload = _jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") not in (None, "access"):
            return False
        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            return False
        return bool(payload.get("sub"))
    except Exception:
        return False


@app.get("/events")
async def events(token: str = ""):
    if not _verify_sse_token(token):
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    q = asyncio.Queue(maxsize=100)
    add_event_queue(q)
    async def event_generator():
        try:
            # 心跳：代理（nginx）默认 60s 空闲断连，定期发注释帧保活
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=_SSE_HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            remove_event_queue(q)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/metrics")
def prometheus_metrics(request: Request):
    """Prometheus 抓取端点。

    配置 CG_METRICS_TOKEN 时按 Bearer 校验；未配置时仅允许环回/私网来源，
    公网访问一律 404（不暴露端点存在性）。
    """
    if settings.metrics_token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {settings.metrics_token}":
            raise HTTPException(status_code=401, detail="Unauthorized")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    client = request.client.host if request.client else ""
    if not _is_private_client(client):
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _is_private_client(host: str) -> bool:
    if host in ("127.0.0.1", "::1", "localhost", ""):
        return True
    try:
        import ipaddress
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False

# 静态文件服务（带缓存头）
class CachedStaticFiles(StaticFiles):
    """为静态资源添加长期缓存头"""
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith(('.js', '.css', '.woff', '.woff2', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg')):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.endswith('.html') or path == '':
            response.headers["Cache-Control"] = "no-cache"
        return response

if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 语音留言密文目录
# 默认不作为静态资源对外暴露：密文文件仅由鉴权后的业务接口读取。
# 如确有外部播放需求，显式设置 CG_SERVE_UPLOADS=1，并在反代层追加访问控制。
def _uploads_dir() -> str:
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(backend_dir, "uploads")


_uploads_path = _uploads_dir()
try:
    os.makedirs(_uploads_path, exist_ok=True)
except OSError:
    logger.warning("uploads directory could not be created at %s", _uploads_path)

if settings.serve_uploads and os.path.isdir(_uploads_path):
    app.mount("/uploads", CachedStaticFiles(directory=_uploads_path), name="uploads")
    logger.warning(
        "CG_SERVE_UPLOADS=1：/uploads 以静态资源对外暴露，请确认反代层已加访问控制")
else:
    logger.info("uploads 目录未对外暴露（默认安全策略）")

_dist_path = os.path.join(base_path, "dist")
if os.path.isdir(_dist_path):
    app.mount("/", CachedStaticFiles(directory=_dist_path, html=True), name="static")
else:
    logger.warning("dist directory not found at %s", _dist_path)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CG_PORT", "8004"))
    # 与 run.py 保持一致：容器内需绑定 0.0.0.0 才能被反代访问
    host = os.environ.get("CG_HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=False, log_level="warning")
