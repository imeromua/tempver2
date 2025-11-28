# epicservice/handlers/archive.py

import logging
import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from config import ADMIN_IDS
from database.orm import orm_get_user_lists_archive, orm_pack_user_files_to_zip
from keyboards.reply import get_archives_submenu_kb, get_main_menu_kb

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 🗂 ПЕРЕГЛЯД АРХІВІВ
# ==============================================================================


@router.message(F.text == "🗂 Переглянути архіви")
async def view_archives(message: Message):
    """Показує список архівів користувача."""
    user_id = message.from_user.id
    archives = await orm_get_user_lists_archive(user_id)

    if not archives:
        await message.answer(
            "🗂 У вас ще немає збережених списків в архіві.",
            reply_markup=get_archives_submenu_kb(),
        )
        return

    # Формуємо список останніх 10 архівів
    text_lines = [f"🗂 **Ваші архіви (останні 10):**\n"]

    for idx, archive in enumerate(archives[:10], start=1):
        date_str = archive.created_at.strftime("%d.%m.%Y %H:%M")
        text_lines.append(f"{idx}. {archive.file_name}\n   📅 {date_str}")

    text_lines.append(
        f"\n📊 Всього збережено: **{len(archives)}** списків\n"
        f"💡 Використайте кнопку '📥 Завантажити все' для отримання повного архіву"
    )

    await message.answer("\n".join(text_lines), reply_markup=get_archives_submenu_kb())


# ==============================================================================
# 📥 ЗАВАНТАЖЕННЯ ОКРЕМОГО АРХІВУ (через номер)
# ==============================================================================


@router.message(F.text.regexp(r"^Завантажити\s+#?\d+$"))
async def download_specific_archive(message: Message):
    """
    Завантажує конкретний архів за номером.
    Приклад: "Завантажити 3" або "Завантажити #3"
    """
    user_id = message.from_user.id

    try:
        # Витягуємо номер
        number_text = message.text.replace("Завантажити", "").replace("#", "").strip()
        archive_number = int(number_text)

        archives = await orm_get_user_lists_archive(user_id)

        if archive_number < 1 or archive_number > len(archives):
            await message.answer(
                f"❌ Невірний номер. Оберіть від 1 до {len(archives)}."
            )
            return

        archive = archives[archive_number - 1]

        if not os.path.exists(archive.file_path):
            await message.answer(
                "❌ Файл не знайдено. Можливо він був видалений."
            )
            return

        # Відправляємо файл
        await message.answer_document(
            FSInputFile(archive.file_path),
            caption=f"📦 {archive.file_name}\n📅 {archive.created_at.strftime('%d.%m.%Y %H:%M')}",
        )

    except ValueError:
        await message.answer("❌ Невірний формат. Використайте: Завантажити 3")
    except Exception as e:
        logger.error("Помилка завантаження архіву: %s", e, exc_info=True)
        await message.answer("❌ Помилка завантаження файлу.")


# ==============================================================================
# 🔙 ПОВЕРНЕННЯ З АРХІВІВ
# ==============================================================================


@router.message(F.text == "🔙 Назад з архівів")
async def back_from_archives(message: Message, state: FSMContext):
    """Повертає з підменю архівів до головного меню."""
    await state.clear()
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS

    await message.answer(
        "🔙 Повернення до головного меню", reply_markup=get_main_menu_kb(is_admin)
    )
