# epicservice/database/orm/analytics.py

import logging
import pandas as pd
from sqlalchemy import select, func, case
from database.engine import sync_session
from database.models import Product, SavedList, SavedListItem, User, StockHistory

logger = logging.getLogger(__name__)

def get_products_dataframe(filter_type: str = "all") -> pd.DataFrame:
    """
    Отримує товари у вигляді DataFrame.
    filter_type: 'all', 'active', 'inactive', 'no_move'
    """
    with sync_session() as session:
        query = select(Product)
        
        if filter_type == "active":
            query = query.where(Product.активний == True)
        elif filter_type == "inactive":
            query = query.where(Product.активний == False)
        elif filter_type == "no_move":
            # Товари, що лежать без руху 3+ місяців
            query = query.where(Product.місяці_без_руху >= 3).order_by(Product.місяці_без_руху.desc())
            
        # Сортування за замовчуванням: Відділ -> Назва
        if filter_type != "no_move":
            query = query.order_by(Product.відділ, Product.назва)
            
        data = session.execute(query).scalars().all()
        
        # Перетворюємо в список словників
        rows = []
        for p in data:
            rows.append({
                "Артикул": p.артикул,
                "Назва": p.назва,
                "Відділ": p.відділ,
                "Група": p.група,
                "Кількість": p.кількість,
                "Ціна": p.ціна,
                "Сума": p.сума_залишку,
                "Без руху (міс)": p.місяці_без_руху,
                "Активний": "Так" if p.активний else "Ні",
                "Оновлено": p.updated_at.strftime("%d.%m.%Y %H:%M") if p.updated_at else ""
            })
            
        return pd.DataFrame(rows)

def get_collected_history_dataframe(days: int = 30) -> pd.DataFrame:
    """
    Отримує історію зібраних товарів за останні N днів.
    """
    with sync_session() as session:
        # Об'єднуємо SavedListItem -> SavedList -> User
        query = (
            select(
                SavedListItem.article_name,
                SavedListItem.quantity,
                SavedList.created_at,
                SavedList.file_name,
                User.username,
                User.first_name,
                User.id
            )
            .join(SavedList, SavedListItem.list_id == SavedList.id)
            .join(User, SavedList.user_id == User.id)
            .order_by(SavedList.created_at.desc())
        )
        
        if days > 0:
            # Тут можна додати фільтр по даті, якщо потрібно
            pass

        results = session.execute(query).all()
        
        rows = []
        for r in results:
            rows.append({
                "Дата": r.created_at.strftime("%d.%m.%Y %H:%M"),
                "Користувач": f"{r.first_name} (@{r.username or '---'})",
                "ID Юзера": r.id,
                "Файл": r.file_name,
                "Товар": r.article_name,
                "Кількість": r.quantity
            })
            
        return pd.DataFrame(rows)

def get_stock_history_dataframe() -> pd.DataFrame:
    """
    Вивантажує історію змін залишків (імпорти, ручні зміни).
    """
    with sync_session() as session:
        # Приєднуємо Product, щоб бачити назву
        query = (
            select(StockHistory, Product.назва)
            .join(Product, StockHistory.product_id == Product.id)
            .order_by(StockHistory.changed_at.desc())
            .limit(2000) # Обмеження для безпеки
        )
        
        results = session.execute(query).all()
        
        rows = []
        for hist, prod_name in results:
            rows.append({
                "Дата": hist.changed_at.strftime("%d.%m.%Y %H:%M"),
                "Артикул": hist.articul,
                "Назва": prod_name,
                "Було": hist.old_quantity,
                "Стало": hist.new_quantity,
                "Джерело": hist.change_source
            })
            
        return pd.DataFrame(rows)