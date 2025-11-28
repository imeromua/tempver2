# epicservice/handlers/user/list_saving.py

import logging
import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from config import ADMIN_IDS
from keyboards.reply import get_main_menu_kb
from utils.list_processor import process_and_save_list

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 💾 ЗБЕРЕЖЕННЯ СПИСКУ
# ==============================================================================


@router.message(F.text == "💾 Зберегти список")
async def save_list_handler(message: Message, state: FSMContext, bot: Bot):
    """Обробляє збереження поточного списку."""
    user_id = message.from_user.id
    msg = await message.answer("⏳ Зберігаю список...")

    main_list_path = None
    surplus_list_path = None

    try:
        # Обробляємо та зберігаємо список (створює власну сесію)
        main_list_path, surplus_list_path = await process_and_save_list(user_id)

        await msg.delete()

        if not main_list_path and not surplus_list_path:
            await message.answer(
                "❌ Список порожній або виникла помилка.\n\n"
                "Переконайтесь, що ви додали товари до списку.",
                reply_markup=get_main_menu_kb(user_id in ADMIN_IDS)
            )
            return

        # Відправляємо основне замовлення
        if main_list_path and os.path.exists(main_list_path):
            await bot.send_document(
                user_id,
                FSInputFile(main_list_path),
                caption="✅ Ваше замовлення\n\nТовари доступні для збору.",
            )
            os.remove(main_list_path)
            logger.info("Відправлено основне замовлення для user_id %s", user_id)

        # Відправляємо дефіцит (якщо є)
        if surplus_list_path and os.path.exists(surplus_list_path):
            await bot.send_document(
                user_id,
                FSInputFile(surplus_list_path),
                caption="⚠️ Дефіцит\n\nЦих товарів недостатньо або немає на складі.",
            )
            os.remove(surplus_list_path)
            logger.info("Відправлено список дефіциту для user_id %s", user_id)

        is_admin = user_id in ADMIN_IDS

        success_message = (
            "✅ Список успішно збережено!\n\n"
            "📦 Файли надіслано вище\n"
            "🗑 Поточний список очищено\n\n"
            "Можете починати новий збір!"
        )

        await message.answer(success_message, reply_markup=get_main_menu_kb(is_admin))

        logger.info("Користувач %s зберіг список", user_id)

    except Exception as e:
        logger.error("Помилка збереження списку для %s: %s", user_id, e, exc_info=True)
        
        try:
            await msg.delete()
        except:
            pass
        
        await message.answer(
            "❌ Помилка збереження списку\n\n"
            "Спробуйте ще раз або зверніться до адміністратора.",
            reply_markup=get_main_menu_kb(user_id in ADMIN_IDS)
        )

        # Видаляємо файли у разі помилки
        if main_list_path and os.path.exists(main_list_path):
            try:
                os.remove(main_list_path)
            except:
                pass
        
        if surplus_list_path and os.path.exists(surplus_list_path):
            try:
                os.remove(surplus_list_path)
            except:
                pass


# ==============================================================================
# 🚫 СКАСУВАННЯ ЗБЕРЕЖЕННЯ
# ==============================================================================


@router.message(F.text == "🚫 Скасувати збереження")
async def cancel_save_handler(message: Message, state: FSMContext):
    """Скасовує процес збереження (якщо є підтвердження)."""
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS

    await state.clear()

    await message.answer(
        "❌ Збереження скасовано.\n\n"
        "Ваш список залишився незмінним.",
        reply_markup=get_main_menu_kb(is_admin),
    )
