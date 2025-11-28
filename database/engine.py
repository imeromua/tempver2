# epicservice/database/engine.py

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from config import DB_NAME, DB_TYPE

logger = logging.getLogger(__name__)


# ==============================================================================
# 🔧 СТВОРЕННЯ ENGINE
# ==============================================================================

if DB_TYPE == "sqlite":
    # SQLite (локальна БД)
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{DB_NAME}",
        echo=False,
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0,  # Timeout для блокувань
        },
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=20,  # Збільшено pool
        max_overflow=40,  # Додаткові підключення
    )

    sync_engine = create_engine(
        f"sqlite:///{DB_NAME}",
        echo=False,
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0,
        },
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=40,
    )

    # ==============================================================================
    # 🔧 НАЛАШТУВАННЯ SQLite PRAGMA
    # ==============================================================================

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """
        Налаштовує SQLite для кращої роботи з паралельними запитами.
        """
        cursor = dbapi_conn.cursor()
        # WAL mode - дозволяє одночасне читання та запис
        cursor.execute("PRAGMA journal_mode=WAL")
        # Timeout для блокувань (30 секунд)
        cursor.execute("PRAGMA busy_timeout=30000")
        # Кешування в пам'яті
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB
        # Синхронізація (NORMAL = баланс швидкості та безпеки)
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Temp store в пам'яті
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.info("SQLite налаштовано з WAL режимом та оптимізаціями")

elif DB_TYPE == "postgres":
    # PostgreSQL (продакшн)
    try:
        from config import DB_HOST, DB_PASS, DB_PORT, DB_USER
    except ImportError:
        raise ValueError(
            "Для PostgreSQL потрібні параметри: DB_HOST, DB_PORT, DB_USER, DB_PASS в config.py"
        )

    DATABASE_URL = (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SYNC_DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    async_engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=40,
        pool_recycle=3600,
    )

    sync_engine = create_engine(
        SYNC_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=40,
        pool_recycle=3600,
    )

    logger.info("PostgreSQL engine створено")

else:
    raise ValueError(f"Невідомий тип БД: {DB_TYPE}. Підтримуються: sqlite, postgres")


# ==============================================================================
# 📦 СТВОРЕННЯ SESSION MAKERS
# ==============================================================================

# Асинхронна сесія (для handlers)
async_session = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Синхронна сесія (для executor та sync функцій)
sync_session = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

logger.info(
    "Підключення до бази даних (синхронне та асинхронне) успішно ініціалізовано."
)


# ==============================================================================
# 🧪 ТЕСТУВАННЯ ПІДКЛЮЧЕННЯ
# ==============================================================================


async def test_connection():
    """Тестує підключення до БД."""
    try:
        async with async_session() as session:
            if DB_TYPE == "sqlite":
                await session.execute("SELECT 1")
            else:
                await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("Помилка підключення до БД: %s", e, exc_info=True)
        return False


def test_connection_sync():
    """Тестує синхронне підключення до БД."""
    try:
        with sync_session() as session:
            session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("Помилка синхронного підключення до БД: %s", e, exc_info=True)
        return False
