# epicservice/handlers/user_search.py

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from thefuzz import fuzz

from database.engine import async_session
from database.orm import orm_search_products_fuzzy

# 👇 ІМПОРТУЄМО НАШУ НОВУ ФУНКЦІЮ
from handlers.user.item_addition import start_quantity_selection

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text)
async def user_search_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    query = message.text.strip()

    if len(query) < 2 or query.startswith(("/", "!", ".", "@")):
        # Можна додати логіку для ігнорування, або підказку
        return

    await message.answer("🔍 Шукаю...")

    try:
        async with async_session() as session:
            results = await orm_search_products_fuzzy(session, query, limit=10)

            if not results:
                await message.answer(f"❌ Нічого не знайдено за запитом: `{query}`")
                return

            # Якщо 1 товар - відразу картка
            if len(results) == 1:
                product = results[0]
                await start_quantity_selection(message, state, product.id)
                return

            # Якщо багато - список з пропозицією обрати
            text_lines = [f"🔍 Знайдено товарів: **{len(results)}**\n"]
            
            # Зберігаємо результати в стан, щоб можна було вибрати номером
            await state.update_data(search_results=[p.id for p in results])
            
            # TODO: Для кращого UX, якщо товарів багато, краще теж робити інлайн-кнопки "Обрати".
            # Але поки лишаємо текстовий вибір, як було, щоб не ламати все одразу.
            
            for idx, product in enumerate(results[:10], start=1):
                text_lines.append(
                    f"/{idx} `{product.артикул}` **{product.назва}** ({product.кількість} шт.)"
                )

            text_lines.append("\nНатисніть на номер (наприклад /1) щоб відкрити картку.")
            await message.answer("\n".join(text_lines))

    except Exception as e:
        logger.error("Search error: %s", e, exc_info=True)
        await message.answer("❌ Помилка пошуку.")

# Обробка натискання на команду /1, /2 тощо
@router.message(F.text.regexp(r"^/\d+$"))
async def select_product_from_search(message: Message, state: FSMContext):
    try:
        idx = int(message.text.replace("/", "")) - 1
        data = await state.get_data()
        results = data.get("search_results", [])
        
        if 0 <= idx < len(results):
            product_id = results[idx]
            await start_quantity_selection(message, state, product_id)
        else:
            await message.answer("❌ Невірний номер.")
            
    except Exception:
        pass