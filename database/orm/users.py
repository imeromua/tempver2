# epicservice/database/orm/users.py

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User

logger = logging.getLogger(__name__)


# ==============================================================================
# 👤 РОБОТА З КОРИСТУВАЧАМИ
# ==============================================================================


async def orm_get_user(session: AsyncSession, user_id: int) -> Optional[User]:
    """
    Отримує користувача за ID.
    """
    try:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(
            "Помилка отримання користувача ID %s: %s", user_id, e, exc_info=True
        )
        return None


async def orm_add_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    first_name: str = "Користувач",
) -> Optional[User]:
    """
    Додає нового користувача або оновлює існуючого.
    Повертає об'єкт користувача.
    """
    try:
        # Перевіряємо чи існує користувач
        existing_user = await orm_get_user(session, user_id)

        if existing_user:
            # Оновлюємо дані
            existing_user.username = username
            existing_user.first_name = first_name
            logger.info("Оновлено дані користувача: %s (@%s)", user_id, username)
            return existing_user
        else:
            # Створюємо нового
            new_user = User(
                id=user_id,
                username=username,
                first_name=first_name,
            )
            session.add(new_user)
            await session.flush()  # Отримуємо ID
            logger.info("Створено нового користувача: %s (@%s)", user_id, username)
            return new_user

    except Exception as e:
        logger.error(
            "Помилка додавання/оновлення користувача ID %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return None


async def orm_get_all_users(session: AsyncSession) -> list[User]:
    """
    Отримує всіх користувачів (для адміна).
    """
    try:
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        return list(result.scalars().all())
    except Exception as e:
        logger.error("Помилка отримання всіх користувачів: %s", e, exc_info=True)
        return []


async def orm_get_users_count(session: AsyncSession) -> int:
    """
    Повертає загальну кількість користувачів.
    """
    try:
        from sqlalchemy import func

        result = await session.execute(select(func.count(User.id)))
        return result.scalar_one()
    except Exception as e:
        logger.error("Помилка підрахунку користувачів: %s", e, exc_info=True)
        return 0
