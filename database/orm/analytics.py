# epicservice/database/orm/analytics.py

import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.engine import sync_session
from database.models import (
    Product,
    SavedList,
    SavedListItem,
    StockHistory,
    TempList,
    User,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 📊 СИНХРОННІ ФУНКЦІЇ (ДЛЯ EXECUTOR)
# ==============================================================================


def orm_get_all_collected_items_sync() -> List[dict]:
    """
    СИНХРОННА функція для отримання всіх зібраних товарів з усіх збережених списків.
    Використовується в executor для генерації звітів.

    Returns:
        Список словників з інформацією про зібрані товари
    """
    try:
        with sync_session() as session:
            # Отримуємо всі позиції з збережених списків
            result = session.execute(
                select(SavedListItem, SavedList)
                .join(SavedList, SavedListItem.list_id == SavedList.id)
                .order_by(SavedList.created_at.desc())
            )

            items = []
            for item, saved_list in result:
                # Парсимо назву товару (формат: "АРТИКУЛ - НАЗВА")
                parts = item.article_name.split(" - ", 1)
                article = parts[0] if len(parts) > 0 else ""
                name = parts[1] if len(parts) > 1 else item.article_name

                items.append(
                    {
                        "article": article,
                        "name": name,
                        "quantity": item.quantity,
                        "user_id": saved_list.user_id,
                        "created_at": saved_list.created_at,
                        "department": "",  # Відділ не зберігається в SavedListItem
                        "group": "",  # Група не зберігається в SavedListItem
                    }
                )

            logger.info("Отримано %s зібраних позицій", len(items))
            return items

    except Exception as e:
        logger.error("Помилка отримання зібраних товарів: %s", e, exc_info=True)
        return []


# ==============================================================================
# 📈 СТАТИСТИКА ПО ТОВАРАХ
# ==============================================================================


def orm_get_top_products(limit: int = 10) -> List[dict]:
    """
    Повертає топ товарів за частотою замовлень.
    """
    try:
        with sync_session() as session:
            # Рахуємо кількість замовлень кожного товару
            result = session.execute(
                select(
                    SavedListItem.article_name,
                    func.sum(SavedListItem.quantity).label("total_quantity"),
                    func.count(SavedListItem.id).label("order_count"),
                )
                .group_by(SavedListItem.article_name)
                .order_by(func.count(SavedListItem.id).desc())
                .limit(limit)
            )

            top_products = []
            for row in result:
                top_products.append(
                    {
                        "article_name": row.article_name,
                        "total_quantity": int(row.total_quantity),
                        "order_count": int(row.order_count),
                    }
                )

            return top_products

    except Exception as e:
        logger.error("Помилка отримання топ товарів: %s", e, exc_info=True)
        return []


def orm_get_department_stats() -> List[dict]:
    """
    Статистика по відділам: кількість товарів, загальна вартість.
    """
    try:
        with sync_session() as session:
            result = session.execute(
                select(
                    Product.відділ,
                    func.count(Product.id).label("product_count"),
                    func.sum(Product.сума_залишку).label("total_value"),
                )
                .where(Product.активний == True)
                .group_by(Product.відділ)
                .order_by(Product.відділ)
            )

            stats = []
            for row in result:
                stats.append(
                    {
                        "department": row.відділ,
                        "product_count": int(row.product_count),
                        "total_value": (
                            float(row.total_value) if row.total_value else 0.0
                        ),
                    }
                )

            return stats

    except Exception as e:
        logger.error("Помилка отримання статистики по відділам: %s", e, exc_info=True)
        return []


# ==============================================================================
# 👥 СТАТИСТИКА ПО КОРИСТУВАЧАХ
# ==============================================================================


def orm_get_user_activity_stats(days: int = 30) -> List[dict]:
    """
    Статистика активності користувачів за вказаний період.
    """
    try:
        with sync_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)

            result = session.execute(
                select(
                    SavedList.user_id,
                    User.username,
                    User.first_name,
                    func.count(SavedList.id).label("list_count"),
                )
                .join(User, SavedList.user_id == User.id)
                .where(SavedList.created_at >= cutoff_date)
                .group_by(SavedList.user_id, User.username, User.first_name)
                .order_by(func.count(SavedList.id).desc())
            )

            stats = []
            for row in result:
                stats.append(
                    {
                        "user_id": row.user_id,
                        "username": row.username or "Невідомо",
                        "first_name": row.first_name,
                        "list_count": int(row.list_count),
                    }
                )

            return stats

    except Exception as e:
        logger.error("Помилка отримання статистики користувачів: %s", e, exc_info=True)
        return []


# ==============================================================================
# 📉 ІСТОРІЯ ЗМІН ЗАЛИШКІВ
# ==============================================================================


def orm_get_stock_history(days: int = 7) -> List[dict]:
    """
    Історія змін залишків за вказаний період.
    """
    try:
        with sync_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)

            result = session.execute(
                select(StockHistory)
                .where(StockHistory.changed_at >= cutoff_date)
                .order_by(StockHistory.changed_at.desc())
            )

            history = []
            for record in result.scalars():
                history.append(
                    {
                        "articul": record.articul,
                        "old_quantity": record.old_quantity,
                        "new_quantity": record.new_quantity,
                        "change_source": record.change_source,
                        "changed_at": record.changed_at,
                    }
                )

            return history

    except Exception as e:
        logger.error("Помилка отримання історії залишків: %s", e, exc_info=True)
        return []


# ==============================================================================
# 📊 ЗАГАЛЬНА СТАТИСТИКА
# ==============================================================================


def orm_get_general_stats() -> dict:
    """
    Загальна статистика для адмін-панелі.
    """
    try:
        with sync_session() as session:
            # Кількість товарів
            products_count = session.execute(
                select(func.count(Product.id)).where(Product.активний == True)
            ).scalar_one()

            # Загальна вартість залишків
            total_value = (
                session.execute(
                    select(func.sum(Product.сума_залишку)).where(
                        Product.активний == True
                    )
                ).scalar_one()
                or 0
            )

            # Кількість користувачів
            users_count = session.execute(select(func.count(User.id))).scalar_one()

            # Кількість збережених списків
            lists_count = session.execute(select(func.count(SavedList.id))).scalar_one()

            # Поточні тимчасові списки
            temp_items = session.execute(select(func.count(TempList.id))).scalar_one()

            return {
                "products_count": products_count,
                "total_value": float(total_value),
                "users_count": users_count,
                "saved_lists_count": lists_count,
                "temp_items_count": temp_items,
            }

    except Exception as e:
        logger.error("Помилка отримання загальної статистики: %s", e, exc_info=True)
        return {
            "products_count": 0,
            "total_value": 0.0,
            "users_count": 0,
            "saved_lists_count": 0,
            "temp_items_count": 0,
        }
