"""数据库引擎配置

生产环境使用 PostgreSQL（支持连接池、并发写入、行级锁），
开发/测试环境可回退到 SQLite（内存或文件）。
通过 CG_DATABASE_URL 环境变量切换。
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from app.config import get_settings

settings = get_settings()

_is_sqlite = "sqlite" in settings.database_url
_is_memory = ":memory:" in settings.database_url

if _is_sqlite:
    # SQLite 不需要连接池
    pool_kwargs = {
        "poolclass": StaticPool if _is_memory else NullPool,
    }
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL / 其他生产级数据库
    pool_kwargs = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
    }
    connect_args = {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.debug,
    **pool_kwargs,
)

# SQLite 开启 WAL 模式提升并发读性能（仅文件模式）
if _is_sqlite and not _is_memory:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：获取数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
