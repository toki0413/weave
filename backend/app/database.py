from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from app.config import get_settings

settings = get_settings()

pool_kwargs = {
    "pool_recycle": 3600,
}
if "sqlite" in settings.database_url:
    # 内存数据库必须用 StaticPool，否则连接关闭后数据消失
    if ":memory:" in settings.database_url:
        pool_kwargs["poolclass"] = StaticPool
    else:
        pool_kwargs["poolclass"] = NullPool
else:
    pool_kwargs["pool_pre_ping"] = True

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=settings.debug,
    **pool_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
