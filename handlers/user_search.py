# epicservice/handlers/user_search.py

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from thefuzz import fuzz

from database.engine import async_session
from database.orm import orm_search_products_fuzzy
from handlers.user.item_addition import (
    ItemAdditionStates,
    start_quantity_selection,
)
from keyboards.reply import get_main_menu_kb

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 🔍 ПОШУК ТОВАРІВ (ПИЛОСОС - ЛОВИТЬ ВЕСЬ ТЕКСТ)
# ==============================================================================


@router.message(F.text)
async def user_search_handler(message: Message, state: FSMContext):
    """
    Пошук товарів за текстом користувача.
    ВАЖЛИВО: Цей handler повинен бути останнім в bot.py!
    Він ловить весь текст, який не обробили інші хендлери.
    """
    user_id = message.from_user.id
    query = message.text.strip()

    # Ігноруємо короткі запити
    if len(query) < 2:
        await message.answer(
            "🔍 Введіть назву або артикул товару (мінімум 2 символи)."
        )
        return

    # Ігноруємо команди та спеціальні символи
    if query.startswith(("/", "!", ".", "@")):
        return

    # Пошук в БД
    await message.answer("🔍 Шукаю...")

    try:
        async with async_session() as session:
            # Спочатку шукаємо точний збіг по артикулу
            results = await orm_search_products_fuzzy(session, query, limit=10)

            if not results:
                await message.answer(
                    f"❌ Нічого не знайдено за запитом: `{query}`\n\n"
                    f"Спробуйте:\n"
                    f"• Артикул товару\n"
                    f"• Назву товару\n"
                    f"• Частину назви"
                )
                return

            # Якщо знайдено тільки 1 товар - відразу переходимо до вибору кількості
            if len(results) == 1:
                product = results[0]
                await message.answer(
                    f"✅ Знайдено: **{product.назва}**\n"
                    f"Артикул: `{product.артикул}`\n"
                    f"Відділ: {product.відділ}\n"
                    f"Залишок: {product.кількість}"
                )
                await start_quantity_selection(message, state, product.id)
                return

            # Якщо знайдено кілька - показуємо список для вибору
            text_lines = [f"🔍 Знайдено товарів: **{len(results)}**\n"]

            for idx, product in enumerate(results[:10], start=1):
                # Рахуємо схожість для сортування
                similarity_name = fuzz.partial_ratio(
                    query.lower(), product.назва.lower()
                )
                similarity_article = fuzz.ratio(
                    query.lower(), product.артикул.lower()
                )
                max_similarity = max(similarity_name, similarity_article)

                text_lines.append(
                    f"{idx}. `{product.артикул}` **{product.назва}**\n"
                    f"   Відділ: {product.відділ} | Залишок: {product.кількість}\n"
                    f"   Схожість: {max_similarity}%\n"
                )

            text_lines.append(
                "\n📝 **Оберіть товар:**\n"
                "Введіть номер (наприклад: `1`) або артикул для уточнення."
            )

            full_text = "\n".join(text_lines)
            if len(full_text) > 4000:
                full_text = full_text[:3900] + "\n... (список обрізано)"

            await message.answer(full_text)

            # Зберігаємо результати пошуку для вибору
            await state.update_data(search_results=[p.id for p in results])
            await state.set_state(ItemAdditionStates.selecting_quantity)

    except Exception as e:
        logger.error("Помилка пошуку товарів: %s", e, exc_info=True)
        await message.answer("❌ Помилка пошуку. Спробуйте ще раз.")


# ==============================================================================
# 🔢 ВИБІР ТОВАРУ ЗІ СПИСКУ РЕЗУЛЬТАТІВ
# ==============================================================================


@router.message(ItemAdditionStates.selecting_quantity, F.text.regexp(r"^\d+$"))
async def select_product_from_results(message: Message, state: FSMContext):
    """
    Обробляє вибір товару за номером зі списку результатів пошуку.
    Приклад: користувач ввів '3' після того, як побачив список товарів.
    """
    data = await state.get_data()
    search_results = data.get("search_results", [])

    # Перевіряємо, чи є збережені результати пошуку
    if not search_results:
        # Якщо немає результатів пошуку, можливо це вибір кількості
        # Передаємо обробку в item_addition.py
        return

    try:
        item_number = int(message.text)

        if item_number < 1 or item_number > len(search_results):
            await message.answer(
                f"❌ Невірний номер. Оберіть від 1 до {len(search_results)}."
            )
            return

        # Отримуємо ID вибраного товару
        selected_product_id = search_results[item_number - 1]

        # Очищаємо результати пошуку зі стану
        await state.update_data(search_results=None)

        # Запускаємо вибір кількості
        async with async_session() as session:
            from database.orm import orm_get_product_by_id

            product = await orm_get_product_by_id(session, selected_product_id)
            if product:
                await message.answer(
                    f"✅ Обрано: **{product.назва}**\n"
                    f"Артикул: `{product.артикул}`"
                )

        await start_quantity_selection(message, state, selected_product_id)

    except ValueError:
        await message.answer("❌ Невірний формат. Введіть номер товару.")
