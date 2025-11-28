# epicservice/handlers/admin/backup_handlers.py

import logging
import os
import shutil
from datetime import datetime

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from config import ADMIN_IDS, BACKUP_DIR, DB_TYPE
from keyboards.reply import get_admin_menu_kb

logger = logging.getLogger(__name__)
router = Router()


# ==============================================================================
# 💾 СТВОРЕННЯ БЕКАПУ
# ==============================================================================


@router.message(F.text == "💾 Створити бекап")
async def create_backup(message: Message):
    """Створює резервну копію бази даних."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    msg = await message.answer("⏳ Створення резервної копії...")

    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if DB_TYPE == "sqlite":
            # Бекап SQLite - просто копіюємо файл
            from config import DB_NAME

            if not os.path.exists(DB_NAME):
                await msg.edit_text("❌ Файл бази даних не знайдено.")
                return

            backup_filename = f"backup_sqlite_{timestamp}.db"
            backup_path = os.path.join(BACKUP_DIR, backup_filename)

            shutil.copy2(DB_NAME, backup_path)

            # Відправляємо файл
            await message.answer_document(
                FSInputFile(backup_path),
                caption=f"💾 **Резервна копія створена**\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            )

            await msg.delete()

            logger.info("Створено бекап SQLite: %s", backup_filename)

        elif DB_TYPE == "postgres":
            # Для PostgreSQL потрібен pg_dump
            await msg.edit_text(
                "⚠️ **Бекап PostgreSQL**\n\n"
                "Для PostgreSQL використовуйте команду:\n"
                "``````\n\n"
                "Або налаштуйте автоматичний бекап на сервері БД."
            )

    except Exception as e:
        logger.error("Помилка створення бекапу: %s", e, exc_info=True)
        await msg.edit_text(f"❌ Помилка створення бекапу:\n{str(e)}")


# ==============================================================================
# 📋 СПИСОК БЕКАПІВ
# ==============================================================================


@router.message(F.text == "📋 Список бекапів")
async def list_backups(message: Message):
    """Показує список доступних бекапів."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    try:
        if not os.path.exists(BACKUP_DIR):
            await message.answer("📭 Немає створених бекапів.")
            return

        # Отримуємо список файлів
        backup_files = []
        for filename in os.listdir(BACKUP_DIR):
            filepath = os.path.join(BACKUP_DIR, filename)
            if os.path.isfile(filepath) and filename.startswith("backup_"):
                file_size = os.path.getsize(filepath)
                file_time = os.path.getmtime(filepath)
                backup_files.append((filename, file_size, file_time))

        if not backup_files:
            await message.answer("📭 Немає створених бекапів.")
            return

        # Сортуємо за датою (новіші спочатку)
        backup_files.sort(key=lambda x: x[2], reverse=True)

        # Формуємо список
        text_lines = [f"💾 **Доступні бекапи:**\n"]

        for idx, (filename, size, timestamp) in enumerate(backup_files[:10], start=1):
            date_str = datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")
            size_mb = size / (1024 * 1024)
            text_lines.append(f"{idx}. `{filename}`\n   📅 {date_str} | 💾 {size_mb:.2f} MB")

        text_lines.append(f"\n📊 Всього бекапів: **{len(backup_files)}**")

        await message.answer("\n".join(text_lines))

    except Exception as e:
        logger.error("Помилка отримання списку бекапів: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")


# ==============================================================================
# 🗑 ОЧИЩЕННЯ СТАРИХ БЕКАПІВ
# ==============================================================================


@router.message(F.text == "🗑 Очистити старі бекапи")
async def cleanup_old_backups(message: Message):
    """Видаляє бекапи старше 30 днів."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    try:
        if not os.path.exists(BACKUP_DIR):
            await message.answer("📭 Немає бекапів для очищення.")
            return

        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(days=30)
        deleted_count = 0

        for filename in os.listdir(BACKUP_DIR):
            filepath = os.path.join(BACKUP_DIR, filename)
            if os.path.isfile(filepath) and filename.startswith("backup_"):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))

                if file_time < cutoff_time:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info("Видалено старий бекап: %s", filename)

        if deleted_count > 0:
            await message.answer(
                f"✅ Видалено старих бекапів: **{deleted_count}**\n"
                f"(старше 30 днів)"
            )
        else:
            await message.answer("✅ Немає старих бекапів для видалення.")

    except Exception as e:
        logger.error("Помилка очищення бекапів: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка: {str(e)}")
