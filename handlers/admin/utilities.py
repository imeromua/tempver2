# epicservice/handlers/admin/utilities.py

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import ADMIN_IDS
from database.engine import async_session
from database.models import User
from keyboards.reply import get_confirmation_kb, get_utilities_menu_kb
from sqlalchemy import func, select

logger = logging.getLogger(__name__)
router = Router()


class UtilityStates(StatesGroup):
    waiting_broadcast_message = State()


# ==============================================================================
# 📢 РОЗСИЛКА
# ==============================================================================


@router.message(F.text == "📢 Розсилка")
async def start_broadcast(message: Message, state: FSMContext):
    """Запускає процес розсилки повідомлення всім користувачам."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await state.set_state(UtilityStates.waiting_broadcast_message)
    await message.answer(
        "📢 **Розсилка повідомлень**\n\n"
        "Надішліть текст повідомлення, яке буде розіслано всім користувачам бота.\n\n"
        "Для скасування використайте /reset"
    )


@router.message(UtilityStates.waiting_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Обробляє та розсилає повідомлення."""
    if message.from_user.id not in ADMIN_IDS:
        return

    broadcast_text = message.text

    # Підтвердження
    await state.update_data(broadcast_text=broadcast_text)
    await message.answer(
        f"📢 **Підтвердіть розсилку:**\n\n{broadcast_text[:500]}\n\n"
        f"⚠️ Повідомлення буде надіслано всім користувачам!",
        reply_markup=get_confirmation_kb(),
    )


@router.message(UtilityStates.waiting_broadcast_message, F.text == "✅ Так, підтверджую")
async def confirm_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Виконує розсилку після підтвердження."""
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")

    if not broadcast_text:
        await message.answer("❌ Помилка: текст не знайдено.")
        await state.clear()
        return

    msg = await message.answer("⏳ Розсилка...")

    try:
        # Отримуємо всіх користувачів
        async with async_session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

        success_count = 0
        blocked_count = 0
        error_count = 0

        for user in users:
            try:
                await bot.send_message(user.id, broadcast_text)
                success_count += 1
                await asyncio.sleep(0.05)  # Throttling
            except Exception as send_error:
                if "bot was blocked" in str(send_error).lower():
                    blocked_count += 1
                else:
                    error_count += 1
                logger.debug("Помилка відправки user_id %s: %s", user.id, send_error)

        await msg.edit_text(
            f"✅ **Розсилка завершена!**\n\n"
            f"📨 Надіслано: **{success_count}**\n"
            f"🚫 Заблокували бота: **{blocked_count}**\n"
            f"❌ Помилок: **{error_count}**"
        )

        await state.clear()

        logger.info(
            "Розсилка завершена: %s успішно, %s заблоковано, %s помилок",
            success_count,
            blocked_count,
            error_count,
        )

    except Exception as e:
        logger.error("Критична помилка розсилки: %s", e, exc_info=True)
        await msg.edit_text(f"❌ Помилка розсилки:\n{str(e)}")
        await state.clear()


@router.message(UtilityStates.waiting_broadcast_message, F.text == "❌ Ні, скасувати")
async def cancel_broadcast(message: Message, state: FSMContext):
    """Скасовує розсилку."""
    await state.clear()
    await message.answer("❌ Розсилка скасована.", reply_markup=get_utilities_menu_kb())


# ==============================================================================
# ✅ ВАЛІДАТОР БД
# ==============================================================================


@router.message(F.text == "✅ Валідатор")
async def validate_database(message: Message):
    """Перевіряє цілісність бази даних."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    msg = await message.answer("⏳ Перевірка бази даних...")

    try:
        issues = []

        async with async_session() as session:
            # Перевірка товарів з невірним форматом кількості
            from database.models import Product

            result = await session.execute(select(Product).where(Product.активний == True))
            products = result.scalars().all()

            invalid_qty_count = 0
            for product in products:
                try:
                    float(str(product.кількість).replace(",", "."))
                except ValueError:
                    invalid_qty_count += 1

            if invalid_qty_count > 0:
                issues.append(f"⚠️ Товарів з невірним форматом кількості: {invalid_qty_count}")

            # Перевірка orphan записів
            from database.models import TempList

            orphan_temp = await session.execute(
                select(func.count(TempList.id))
                .outerjoin(User, TempList.user_id == User.id)
                .where(User.id == None)
            )
            orphan_count = orphan_temp.scalar_one()

            if orphan_count > 0:
                issues.append(f"⚠️ Orphan записів у temp_lists: {orphan_count}")

        # Результат
        if issues:
            result_text = "⚠️ **Виявлено проблеми:**\n\n" + "\n".join(issues)
        else:
            result_text = "✅ **База даних в порядку!**\n\nПроблем не виявлено."

        await msg.edit_text(result_text)

    except Exception as e:
        logger.error("Помилка валідації БД: %s", e, exc_info=True)
        await msg.edit_text(f"❌ Помилка валідації:\n{str(e)}")


# ==============================================================================
# 🔄 КОНВЕРТЕР
# ==============================================================================


@router.message(F.text == "🔄 Конвертер")
async def converter_utility(message: Message):
    """Утиліта для конвертації форматів."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "🔄 **Конвертер**\n\n"
        "Функція в розробці.\n\n"
        "Планується:\n"
        "• Конвертація .xls → .xlsx\n"
        "• Конвертація .ods → .xlsx\n"
        "• Нормалізація форматів даних"
    )
