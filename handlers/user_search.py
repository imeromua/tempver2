# epicservice/handlers/user_search.py

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database.engine import async_session
from database.orm import orm_search_products_fuzzy
from handlers.user.item_addition import start_quantity_selection
from keyboards.inline import get_search_results_kb

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# 🔍 ПОШУК ТОВАРІВ
# ==============================================================================

@router.message(F.text)
async def user_search_handler(message: Message, state: FSMContext):
    """
    Пошук товарів за текстом користувача.
    """
    query = message.text.strip()

    # Ігноруємо короткі запити та команди
    if len(query) < 2 or query.startswith(("/", "!", ".", "@")):
        return

    await message.answer("🔍 Шукаю...")

    try:
        async with async_session() as session:
            # Шукаємо товари
            results = await orm_search_products_fuzzy(session, query, limit=10)

            if not results:
                await message.answer(f"❌ Нічого не знайдено за запитом: `{query}`")
                return

            # Якщо знайдено тільки 1 товар - відразу картка
            if len(results) == 1:
                product = results[0]
                await start_quantity_selection(message, state, product.id)
                return

            # Якщо знайдено кілька - показуємо інлайн кнопки
            await message.answer(
                f"🔍 Знайдено товарів: **{len(results)}**\nОберіть потрібний:",
                reply_markup=get_search_results_kb(results)
            )

    except Exception as e:
        logger.error("Помилка пошуку товарів: %s", e, exc_info=True)
        await message.answer("❌ Помилка пошуку. Спробуйте ще раз.")


# ==============================================================================
# 🔢 ВИБІР ТОВАРУ (CALLBACK)
# ==============================================================================

@router.callback_query(F.data.startswith("search:prod:"))
async def process_search_selection(callback: CallbackQuery, state: FSMContext):
    """Обробляє натискання на товар у результатах пошуку."""
    try:
        # data format: search:prod:ID
        _, _, product_id_str = callback.data.split(":")
        product_id = int(product_id_str)

        # Видаляємо повідомлення з результатами пошуку, щоб не засмічувати
        await callback.message.delete()

        # Відкриваємо картку товару
        await start_quantity_selection(callback.message, state, product_id)
        
    except Exception as e:
        logger.error("Error selecting product: %s", e)
        await callback.answer("❌ Помилка вибору", show_alert=True)