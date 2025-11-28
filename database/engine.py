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
    # SQLite (локальна БД - залишаємо для сумісності)
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
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.info("SQLite налаштовано з WAL режимом та оптимізаціями")

elif DB_TYPE == "postgres":
    # PostgreSQL (ОНОВЛЕНА КОНФІГУРАЦІЯ)
    try:
        from config import DB_HOST, DB_PASS, DB_PORT, DB_USER
    except ImportError:
        raise ValueError(
            "Для PostgreSQL потрібні параметри: DB_HOST, DB_PORT, DB_USER, DB_PASS в config.py"
        )

    # Формуємо URL підключення
    DATABASE_URL = (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SYNC_DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # Асинхронний рушій (Основний)
    async_engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,  # Перевіряє з'єднання перед видачею
        pool_size=20,        # Розмір пулу з'єднань
        max_overflow=40,     # Максимальна кількість додаткових з'єднань
        pool_recycle=3600,   # Перезапускати з'єднання щогодини
        # ВАЖЛИВО: Встановлюємо рівень ізоляції для коректної роботи транзакцій
        isolation_level="READ COMMITTED",
    )

    # Синхронний рушій (Для звітів та міграцій)
    sync_engine = create_engine(
        SYNC_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
    )

    logger.info("✅ PostgreSQL engine успішно ініціалізовано (Local Mode)")

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
            # PostgreSQL вимагає коректного синтаксису навіть для тестів
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Помилка підключення до БД: %s", e, exc_info=True)
        return False


def test_connection_sync():
    """Тестує синхронне підключення до БД."""
    try:
        with sync_session() as session:
            from sqlalchemy import text
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Помилка синхронного підключення до БД: %s", e, exc_info=True)
        return False