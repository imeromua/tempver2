# epicservice/database/orm/products.py

import asyncio
import logging
import re
import pandas as pd
from typing import Dict, Any, List

from sqlalchemy import select, update, insert, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from thefuzz import fuzz

from database.engine import async_session, sync_session
from database.models import Product, StockHistory
from utils.import_parser import ImportParser

logger = logging.getLogger(__name__)


# --- Допоміжні функції ---

def _extract_article(name_str: str) -> str | None:
    """
    Витягує артикул з початку рядка назви товару.
    Необхідно для сумісності з database/orm/archives.py
    """
    if not isinstance(name_str, str):
        name_str = str(name_str)
    # Шукаємо 8 або більше цифр на початку рядка
    match = re.match(r"^(\d{8,})", name_str.strip())
    return match.group(1) if match else None


# --- Логіка Імпорту ---

def _sync_incremental_import(file_path: str, user_id: int) -> dict:
    """
    Синхронна функція інкрементального імпорту.
    Виконує 'розумне' оновлення бази даних на основі файлу.
    """
    # 1. Парсинг файлу
    parser = ImportParser(file_path)
    if not parser.load_file():
        return {'error': 'Не вдалося прочитати файл', 'details': parser.validation_errors}

    items, errors = parser.parse_data()
    if not items:
        return {'error': 'У файлі не знайдено валідних товарів', 'details': errors}
    
    # Словник нових даних: {articul: item_dict}
    new_data_map = {item['артикул']: item for item in items}
    new_articles = set(new_data_map.keys())

    stats = {
        'added': 0, 
        'updated': 0, 
        'deactivated': 0, 
        'reactivated': 0,
        'total_in_db': 0, 
        'errors': errors, 
        'department_stats': {},
        'price_warnings': [] # Для майбутніх звітів про різку зміну ціни
    }

    with sync_session() as session:
        # 2. Отримуємо всі існуючі товари з БД
        existing_products = {p.артикул: p for p in session.execute(select(Product)).scalars()}
        db_articles = set(existing_products.keys())

        # 3. Визначаємо групи товарів
        to_add = new_articles - db_articles
        to_process_existing = new_articles.intersection(db_articles)
        to_archive = db_articles - new_articles # Ті, що є в БД, але зникли з файлу

        # 4. Деактивація (Архівування) зниклих товарів
        if to_archive:
            # Оновлюємо тільки ті, що зараз активні
            active_to_archive = [art for art in to_archive if existing_products[art].активний]
            if active_to_archive:
                stmt = update(Product).where(
                    Product.артикул.in_(active_to_archive)
                ).values(активний=False)
                res = session.execute(stmt)
                stats['deactivated'] = res.rowcount
                
                # Запис в історію: кількість стала 0 (зник з прайсу)
                history_entries = []
                for art in active_to_archive:
                    prod = existing_products[art]
                    history_entries.append(StockHistory(
                        product_id=prod.id, 
                        articul=art,
                        old_quantity=str(prod.кількість), 
                        new_quantity="0",
                        change_source="import_missing"
                    ))
                session.add_all(history_entries)

        # 5. Оновлення існуючих товарів
        history_updates = []
        updates_mappings = []

        for art in to_process_existing:
            prod = existing_products[art]
            new_item = new_data_map[art]
            
            is_modified = False
            
            # А. Реактивація (якщо товар повернувся)
            if not prod.активний:
                new_item['активний'] = True
                stats['reactivated'] += 1
                is_modified = True

            # Б. Перевірка зміни кількості
            old_qty_float = float(prod.кількість) if prod.кількість else 0.0
            new_qty_float = float(new_item['кількість'])
            
            if abs(old_qty_float - new_qty_float) > 0.001:
                history_updates.append(StockHistory(
                    product_id=prod.id, 
                    articul=art,
                    old_quantity=str(prod.кількість), 
                    new_quantity=new_item['кількість'],
                    change_source="import_update"
                ))
                is_modified = True
            
            # В. Перевірка ціни (лог можливих помилок)
            old_price = prod.ціна or 0.0
            new_price = new_item['ціна']
            if old_price > 0 and new_price > 0:
                change_percent = abs(new_price - old_price) / old_price
                if change_percent > 0.5: # Якщо ціна змінилась більше ніж на 50%
                    stats['price_warnings'].append(f"Арт {art}: {old_price:.2f} -> {new_price:.2f}")

            # Додаємо ID для оновлення
            updates_mappings.append({
                "id": prod.id,
                "артикул": art,
                **new_item
            })
            stats['updated'] += 1

        # Виконуємо масове оновлення
        if updates_mappings:
            session.bulk_update_mappings(Product, updates_mappings)
        if history_updates:
            session.add_all(history_updates)

        # 6. Додавання нових товарів
        if to_add:
            new_objects = [Product(**new_data_map[art]) for art in to_add]
            session.bulk_save_objects(new_objects)
            stats['added'] = len(new_objects)

        # 7. Скидання резервів
        # При новому імпорті старі резерви стають неактуальними, бо прийшов "факт"
        session.execute(update(Product).values(відкладено=0))

        session.commit()
        
        # 8. Фінальна статистика
        stats['total_in_db'] = session.execute(select(func.count(Product.id)).where(Product.активний == True)).scalar_one()
        
        # Статистика по відділах (з файлу)
        for item in items:
            d = item['відділ']
            stats['department_stats'][d] = stats['department_stats'].get(d, 0) + 1

    return stats


async def orm_smart_import(file_path: str, user_id: int) -> dict:
    """
    Асинхронна обгортка для імпорту.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_incremental_import, file_path, user_id)


# --- Функції пошуку та роботи з товарами ---

async def orm_find_products(search_query: str) -> list[Product]:
    """
    Виконує нечіткий пошук товарів.
    """
    async with async_session() as session:
        like_query = f"%{search_query}%"
        stmt = select(Product).where(
            Product.активний == True,
            (Product.назва.ilike(like_query)) | (Product.артикул.ilike(like_query))
        )
        result = await session.execute(stmt)
        candidates = result.scalars().all()

        if not candidates: return []

        scored_products = []
        search_query_lower = search_query.lower()

        for product in candidates:
            if search_query == product.артикул: article_score = 200
            else: article_score = fuzz.ratio(search_query, product.артикул) * 1.5

            name_lower = product.назва.lower()
            token_set_score = fuzz.token_set_ratio(search_query_lower, name_lower)
            partial_score = fuzz.partial_ratio(search_query_lower, name_lower)
            
            if name_lower.startswith(search_query_lower): name_score = 100
            else: name_score = (token_set_score * 0.7) + (partial_score * 0.3)

            final_score = max(article_score, name_score)

            if final_score > 65:
                scored_products.append((product, final_score))
        
        scored_products.sort(key=lambda x: x[1], reverse=True)
        return [product for product, score in scored_products[:15]]

async def orm_get_product_by_id(session, product_id: int, for_update: bool = False) -> Product | None:
    query = select(Product).where(Product.id == product_id)
    # for_update ігнорується на SQLite, але залишаємо для сумісності з Postgres
    if for_update and session.bind.dialect.name != 'sqlite':
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()

def orm_get_all_products_sync() -> list[Product]:
    with sync_session() as session:
        query = select(Product).where(Product.активний == True).order_by(Product.відділ, Product.назва)
        result = session.execute(query)
        return result.scalars().all()

def _sync_subtract_collected_from_stock(dataframe: pd.DataFrame) -> dict:
    processed_count, not_found_count, error_count = 0, 0, 0
    with sync_session() as session:
        for _, row in dataframe.iterrows():
            article = str(row.get("артикул", "")).strip()
            if not article: continue

            product = session.execute(select(Product).where(Product.артикул == article)).scalar_one_or_none()
            if not product:
                not_found_count += 1
                continue

            try:
                current_stock = float(str(product.кількість).replace(',', '.'))
                quantity_to_subtract = float(str(row["кількість"]).replace(',', '.'))
                
                new_stock = current_stock - quantity_to_subtract
                price = product.ціна or 0.0
                new_stock_sum = new_stock * price

                session.execute(
                    update(Product)
                    .where(Product.id == product.id)
                    .values(
                        кількість=str(new_stock),
                        сума_залишку=new_stock_sum
                    )
                )
                processed_count += 1
            except (ValueError, TypeError):
                error_count += 1
                continue
        session.commit()
    return {'processed': processed_count, 'not_found': not_found_count, 'errors': error_count}


async def orm_subtract_collected(dataframe: pd.DataFrame) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_subtract_collected_from_stock, dataframe)