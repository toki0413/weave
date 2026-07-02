from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
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
from app.routers import auth, session, graph, baseline, stt, state_sync, backup, scale, lexicon, decline, notification, voice_message, family_sync, share, training, llm, websocket, sync
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
# 文件轮转
file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler = RotatingFileHandler(
    log_dir / "app.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(file_fmt)
file_handler.setLevel(log_level)
root_logger.addHandler(file_handler)

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
    """迁移前自动备份数据库，仅保留最近3个备份"""
    db_path = _get_db_path()
    if not db_path.exists():
        return
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}.backup.{timestamp}{db_path.suffix}"
    import shutil
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


def _run_migrations():
    """执行数据库迁移，失败则降级到 create_all 保证可用性"""
    auto_migrate = os.environ.get("CG_AUTO_MIGRATE", "1") == "1"
    if not auto_migrate:
        logger.info("CG_AUTO_MIGRATE=0，跳过 alembic 自动迁移")
        Base.metadata.create_all(bind=engine)
        return

    _backup_db_before_migration()

    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
        command.upgrade(alembic_cfg, "head")
        logger.info("数据库迁移完成")
    except Exception as e:
        logger.warning("alembic 迁移失败，降级到 create_all: %s", e)
        logger.warning("如需跳过自动迁移，可设置环境变量 CG_AUTO_MIGRATE=0")
        Base.metadata.create_all(bind=engine)

_run_migrations()

# 初始化 Redis（限流、SSE Pub/Sub、token 黑名单共享）
from app.redis_client import init_redis
init_redis()

# 初始化 KMS（主密钥包装/解包）
from app.services.kms import init_kms
init_kms()

app = FastAPI(
    title="Cognitive Garden API",
    description="织忆·认知花园 - 认知辅助工具后端",
    version="2.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# 请求/响应日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        "%s %s %d - %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response

# Prometheus 指标中间件
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    ACTIVE_CONNECTIONS.inc()
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_LATENCY.observe(duration)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    ACTIVE_CONNECTIONS.dec()
    return response

# 全局异常处理：生产环境不暴露内部堆栈，但提示日志位置便于排查
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    if settings.debug:
        detail = str(exc)
    else:
        log_file = log_dir / "app.log"
        detail = f"服务出现内部错误，请联系技术支持并提供日志文件：{log_file}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "log_path": str(log_dir / "app.log")},
    )

# CORS：生产环境仅允许 Tauri WebView；开发环境额外放行 Vite dev server
_cors_origins = [
    "tauri://localhost",
    "https://tauri.localhost",
]
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
    allow_headers=["*"],
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
v1_app.include_router(llm.router)
v1_app.include_router(websocket.router)
v1_app.include_router(sync.router)

# 为 v1_app 也添加全局异常处理，确保挂载后的路由也能捕获异常
@v1_app.exception_handler(Exception)
async def v1_global_exception_handler(request, exc):
    logger.error("Unhandled exception in v1: %s", exc, exc_info=True)
    if settings.debug:
        detail = str(exc)
    else:
        log_file = log_dir / "app.log"
        detail = f"服务出现内部错误，请联系技术支持并提供日志文件：{log_file}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "log_path": str(log_dir / "app.log")},
    )

app.mount("/api/v1", v1_app)

@app.get("/api")
def api_redirect():
    return RedirectResponse(url="/api/v1")

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    version = "2.1.0"
    db_connected = False
    disk_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False
    try:
        db_path = _get_db_path()
        if db_path.exists():
            disk = shutil.disk_usage(db_path.parent)
            disk_ok = disk.free > 100 * 1024 * 1024  # 100MB
        else:
            disk_ok = True
    except Exception:
        disk_ok = False
    return {
        "status": "ok" if db_connected and disk_ok else "degraded",
        "version": version,
        "db_connected": db_connected,
        "disk_ok": disk_ok,
    }

# SSE 实时通知
from app.services.events import add_event_queue, remove_event_queue

@app.get("/events")
async def events():
    q = asyncio.Queue(maxsize=100)
    add_event_queue(q)
    async def event_generator():
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            remove_event_queue(q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

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

# 语音留言上传文件静态服务
_backend_dir = os.path.dirname(os.path.dirname(__file__))
_uploads_path = os.path.join(_backend_dir, "uploads")
if os.path.isdir(_uploads_path):
    app.mount("/uploads", CachedStaticFiles(directory=_uploads_path), name="uploads")
else:
    # 确保开发环境下 uploads 目录存在
    try:
        os.makedirs(_uploads_path, exist_ok=True)
        app.mount("/uploads", CachedStaticFiles(directory=_uploads_path), name="uploads")
    except OSError:
        logger.warning("uploads directory not found and could not be created at %s", _uploads_path)

_dist_path = os.path.join(base_path, "dist")
if os.path.isdir(_dist_path):
    app.mount("/", CachedStaticFiles(directory=_dist_path, html=True), name="static")
else:
    logger.warning("dist directory not found at %s", _dist_path)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CG_PORT", "8004"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False, log_level="warning")
