# epicservice/database/orm/temp_lists.py

import logging
from typing import List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.engine import async_session
from database.models import Product, TempList

logger = logging.getLogger(__name__)


# ==============================================================================
# 📋 ОТРИМАННЯ ТИМЧАСОВОГО СПИСКУ
# ==============================================================================


async def orm_get_temp_list(user_id: int) -> List[TempList]:
    """
    Отримує тимчасовий список користувача з завантаженими товарами.
    Повертає список відсортований за ID.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(TempList)
                .options(joinedload(TempList.product))
                .where(TempList.user_id == user_id)
                .order_by(TempList.id)
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(
            "Помилка отримання тимчасового списку для user_id %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return []


async def orm_get_temp_list_department(user_id: int) -> Optional[int]:
    """
    Повертає відділ, до якого належать товари в тимчасовому списку користувача.
    Якщо список порожній, повертає None.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Product.відділ)
                .join(TempList, TempList.product_id == Product.id)
                .where(TempList.user_id == user_id)
                .limit(1)
            )
            department = result.scalar_one_or_none()
            return department
    except Exception as e:
        logger.error(
            "Помилка отримання відділу для user_id %s: %s", user_id, e, exc_info=True
        )
        return None


async def orm_get_temp_list_item(
    user_id: int, product_id: int
) -> Optional[TempList]:
    """
    Отримує конкретну позицію з тимчасового списку користувача.
    Повертає None, якщо товар не знайдено.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(TempList).where(
                    and_(
                        TempList.user_id == user_id, TempList.product_id == product_id
                    )
                )
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error(
            "Помилка отримання позиції списку (user_id=%s, product_id=%s): %s",
            user_id,
            product_id,
            e,
            exc_info=True,
        )
        return None


# ==============================================================================
# ➕ ДОДАВАННЯ ДО СПИСКУ
# ==============================================================================


async def orm_add_item_to_temp_list(
    user_id: int, product_id: int, quantity: int
) -> bool:
    """
    Додає товар до тимчасового списку або збільшує кількість, якщо вже є.
    Повертає True при успіху.
    """
    try:
        async with async_session() as session:
            # Перевіряємо, чи вже є товар в списку
            existing = await session.execute(
                select(TempList).where(
                    and_(
                        TempList.user_id == user_id, TempList.product_id == product_id
                    )
                )
            )
            existing_item = existing.scalar_one_or_none()

            if existing_item:
                # Збільшуємо кількість
                existing_item.quantity += quantity
                logger.info(
                    "Збільшено кількість товару (user_id=%s, product_id=%s): %s -> %s",
                    user_id,
                    product_id,
                    existing_item.quantity - quantity,
                    existing_item.quantity,
                )
            else:
                # Додаємо новий товар
                new_item = TempList(
                    user_id=user_id, product_id=product_id, quantity=quantity
                )
                session.add(new_item)
                logger.info(
                    "Додано товар до списку (user_id=%s, product_id=%s, quantity=%s)",
                    user_id,
                    product_id,
                    quantity,
                )

            await session.commit()
            return True

    except Exception as e:
        logger.error(
            "Помилка додавання товару до списку (user_id=%s, product_id=%s): %s",
            user_id,
            product_id,
            e,
            exc_info=True,
        )
        return False


# ==============================================================================
# ✏️ РЕДАГУВАННЯ СПИСКУ
# ==============================================================================


async def orm_update_item_quantity(
    session: AsyncSession, item_id: int, new_quantity: int
) -> bool:
    """
    Оновлює кількість товару в тимчасовому списку.
    Якщо нова кількість <= 0, видаляє товар зі списку.
    
    Примітка: Ця функція приймає session як параметр і НЕ створює власну.
    """
    try:
        if new_quantity <= 0:
            # Видаляємо через ту ж сесію
            await session.execute(delete(TempList).where(TempList.id == item_id))
            await session.commit()
            logger.info("Видалено позицію ID %s (кількість <= 0)", item_id)
            return True

        result = await session.execute(select(TempList).where(TempList.id == item_id))
        item = result.scalar_one_or_none()

        if not item:
            logger.warning("Позиція ID %s не знайдена для оновлення", item_id)
            return False

        old_quantity = item.quantity
        item.quantity = new_quantity
        await session.commit()

        logger.info(
            "Оновлено кількість позиції ID %s: %s -> %s",
            item_id,
            old_quantity,
            new_quantity,
        )
        return True

    except Exception as e:
        await session.rollback()
        logger.error(
            "Помилка оновлення кількості позиції ID %s: %s", item_id, e, exc_info=True
        )
        return False


async def orm_delete_item_from_temp_list(item_id: int) -> bool:
    """Видаляє товар з тимчасового списку за ID позиції."""
    try:
        async with async_session() as session:
            await session.execute(delete(TempList).where(TempList.id == item_id))
            await session.commit()
            logger.info("Видалено позицію ID %s з тимчасового списку", item_id)
            return True

    except Exception as e:
        logger.error(
            "Помилка видалення позиції ID %s: %s", item_id, e, exc_info=True
        )
        return False


async def orm_clear_temp_list(user_id: int) -> bool:
    """Очищає весь тимчасовий список користувача."""
    try:
        async with async_session() as session:
            result = await session.execute(
                delete(TempList).where(TempList.user_id == user_id)
            )
            deleted_count = result.rowcount
            await session.commit()

            logger.info(
                "Очищено тимчасовий список user_id %s (видалено %s позицій)",
                user_id,
                deleted_count,
            )
            return True

    except Exception as e:
        logger.error(
            "Помилка очищення списку user_id %s: %s", user_id, e, exc_info=True
        )
        return False


# ==============================================================================
# 📊 СТАТИСТИКА ТА РЕЗЕРВИ
# ==============================================================================


async def orm_get_total_temp_reservation_for_product(product_id: int) -> int:
    """
    Повертає загальну кількість товару, зарезервовану в тимчасових списках ВСІХ користувачів.
    Використовується для розрахунку доступних залишків.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(func.sum(TempList.quantity)).where(
                    TempList.product_id == product_id
                )
            )
            total = result.scalar_one_or_none()
            return int(total) if total else 0

    except Exception as e:
        logger.error(
            "Помилка отримання резерву для product_id %s: %s",
            product_id,
            e,
            exc_info=True,
        )
        return 0


async def orm_get_temp_list_summary(user_id: int) -> dict:
    """
    Повертає статистику по тимчасовому списку користувача.
    """
    try:
        temp_list = await orm_get_temp_list(user_id)

        total_items = len(temp_list)
        total_quantity = sum(item.quantity for item in temp_list)
        departments = set(item.product.відділ for item in temp_list)

        return {
            "total_items": total_items,
            "total_quantity": total_quantity,
            "departments": list(departments),
            "is_empty": total_items == 0,
        }

    except Exception as e:
        logger.error(
            "Помилка отримання статистики списку user_id %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return {
            "total_items": 0,
            "total_quantity": 0,
            "departments": [],
            "is_empty": True,
        }
