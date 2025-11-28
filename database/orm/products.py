# epicservice/database/orm/products.py

import logging
from typing import List, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Product

logger = logging.getLogger(__name__)


# ==============================================================================
# 📦 ОТРИМАННЯ ТОВАРІВ
# ==============================================================================


async def orm_get_product_by_id(
    session: AsyncSession, product_id: int
) -> Optional[Product]:
    """Отримує товар за ID."""
    try:
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error("Помилка отримання товару ID %s: %s", product_id, e, exc_info=True)
        return None


async def orm_get_product_by_article(
    session: AsyncSession, article: str
) -> Optional[Product]:
    """Отримує товар за артикулом."""
    try:
        result = await session.execute(
            select(Product).where(Product.артикул == article.strip())
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error("Помилка отримання товару за артикулом %s: %s", article, e, exc_info=True)
        return None


async def orm_get_all_products(session: AsyncSession, active_only: bool = True) -> List[Product]:
    """Отримує всі товари (опціонально тільки активні)."""
    try:
        query = select(Product)
        if active_only:
            query = query.where(Product.активний == True)
        result = await session.execute(query)
        return list(result.scalars().all())
    except Exception as e:
        logger.error("Помилка отримання всіх товарів: %s", e, exc_info=True)
        return []


# ==============================================================================
# 🔍 ПОШУК ТОВАРІВ
# ==============================================================================


async def orm_search_products_fuzzy(
    session: AsyncSession, query: str, limit: int = 10
) -> List[Product]:
    """
    Нечіткий пошук товарів за назвою або артикулом.
    Повертає тільки активні товари.
    """
    try:
        search_pattern = f"%{query.strip()}%"

        result = await session.execute(
            select(Product)
            .where(
                and_(
                    Product.активний == True,
                    or_(
                        Product.назва.ilike(search_pattern),
                        Product.артикул.ilike(search_pattern),
                    ),
                )
            )
            .limit(limit)
        )
        return list(result.scalars().all())
    except Exception as e:
        logger.error("Помилка пошуку товарів за запитом '%s': %s", query, e, exc_info=True)
        return []


async def orm_search_products_by_department(
    session: AsyncSession, department: int, query: str = "", limit: int = 50
) -> List[Product]:
    """Пошук товарів за відділом з опціональним фільтром."""
    try:
        base_query = select(Product).where(
            and_(Product.активний == True, Product.відділ == department)
        )

        if query:
            search_pattern = f"%{query.strip()}%"
            base_query = base_query.where(
                or_(
                    Product.назва.ilike(search_pattern),
                    Product.артикул.ilike(search_pattern),
                )
            )

        result = await session.execute(base_query.limit(limit))
        return list(result.scalars().all())
    except Exception as e:
        logger.error("Помилка пошуку товарів за відділом %s: %s", department, e, exc_info=True)
        return []


# ==============================================================================
# ✏️ ОНОВЛЕННЯ ТОВАРІВ
# ==============================================================================


async def orm_update_product_quantity(
    session: AsyncSession, product_id: int, new_quantity: str
) -> bool:
    """
    Оновлює кількість товару за ID.
    Приймає кількість як рядок (формат БД).
    """
    try:
        await session.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(кількість=new_quantity)
        )
        await session.commit()
        logger.info("Оновлено кількість товару ID %s: %s", product_id, new_quantity)
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Помилка оновлення кількості товару ID %s: %s", product_id, e, exc_info=True)
        return False


async def orm_update_product_reserved(
    session: AsyncSession, product_id: int, new_reserved: int
) -> bool:
    """Оновлює кількість відкладеного товару."""
    try:
        await session.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(відкладено=new_reserved)
        )
        await session.commit()
        logger.info("Оновлено відкладено для товару ID %s: %s", product_id, new_reserved)
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Помилка оновлення відкладеного товару ID %s: %s", product_id, e, exc_info=True)
        return False


async def orm_deactivate_product(session: AsyncSession, product_id: int) -> bool:
    """Деактивує товар (не видаляє з БД)."""
    try:
        await session.execute(
            update(Product).where(Product.id == product_id).values(активний=False)
        )
        await session.commit()
        logger.info("Деактивовано товар ID %s", product_id)
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Помилка деактивації товару ID %s: %s", product_id, e, exc_info=True)
        return False


# ==============================================================================
# 📊 СТАТИСТИКА
# ==============================================================================


async def orm_get_products_count(session: AsyncSession, active_only: bool = True) -> int:
    """Повертає кількість товарів в БД."""
    try:
        query = select(func.count(Product.id))
        if active_only:
            query = query.where(Product.активний == True)
        result = await session.execute(query)
        return result.scalar_one()
    except Exception as e:
        logger.error("Помилка підрахунку товарів: %s", e, exc_info=True)
        return 0


async def orm_get_total_stock_value(session: AsyncSession) -> float:
    """Повертає загальну вартість залишків."""
    try:
        result = await session.execute(
            select(func.sum(Product.сума_залишку)).where(Product.активний == True)
        )
        total = result.scalar_one_or_none()
        return float(total) if total else 0.0
    except Exception as e:
        logger.error("Помилка розрахунку вартості залишків: %s", e, exc_info=True)
        return 0.0


# ==============================================================================
# 🛡️ ВАЛІДАЦІЯ КІЛЬКОСТІ
# ==============================================================================


def validate_product_quantity(quantity_str: str) -> Optional[float]:
    """
    Валідує та конвертує кількість товару з рядка в float.
    Повертає None якщо формат невірний.
    """
    try:
        # Замінюємо кому на крапку
        cleaned = str(quantity_str).replace(",", ".").strip()
        value = float(cleaned)
        return value if value >= 0 else None
    except (ValueError, TypeError, AttributeError):
        logger.warning("Невірний формат кількості: %s", quantity_str)
        return None


def get_available_quantity(product: Product, temp_reserved: int = 0) -> int:
    """
    Розраховує доступну кількість товару.
    Враховує відкладено (permanently_reserved) та тимчасові резерви (temp_reserved).
    """
    try:
        stock_qty = validate_product_quantity(product.кількість)
        if stock_qty is None:
            logger.error("Невірна кількість для товару ID %s: %s", product.id, product.кількість)
            return 0

        permanently_reserved = product.відкладено or 0
        available = int(stock_qty - permanently_reserved - temp_reserved)
        return max(0, available)  # Не може бути менше 0
    except Exception as e:
        logger.error("Помилка розрахунку доступної кількості для товару ID %s: %s", product.id, e, exc_info=True)
        return 0
