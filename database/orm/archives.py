# epicservice/database/orm/archives.py

import logging
import os
import shutil
import zipfile
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import ARCHIVES_PATH
from database.engine import async_session
from database.models import SavedList, SavedListItem

logger = logging.getLogger(__name__)


# ==============================================================================
# 📂 ОТРИМАННЯ АРХІВІВ
# ==============================================================================


async def orm_get_user_lists_archive(user_id: int) -> List[SavedList]:
    """
    Отримує всі збережені списки користувача, відсортовані за датою (новіші спочатку).
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SavedList)
                .where(SavedList.user_id == user_id)
                .order_by(SavedList.created_at.desc())
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(
            "Помилка отримання архівів для user_id %s: %s", user_id, e, exc_info=True
        )
        return []


async def orm_get_all_archives() -> List[SavedList]:
    """
    Отримує всі збережені списки всіх користувачів (для адміна).
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SavedList).order_by(SavedList.created_at.desc())
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error("Помилка отримання всіх архівів: %s", e, exc_info=True)
        return []


async def orm_get_saved_list_items(list_id: int) -> List[SavedListItem]:
    """
    Отримує всі позиції конкретного збереженого списку.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SavedListItem).where(SavedListItem.list_id == list_id)
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(
            "Помилка отримання позицій списку ID %s: %s", list_id, e, exc_info=True
        )
        return []


# ==============================================================================
# 🗑️ ВИДАЛЕННЯ АРХІВІВ
# ==============================================================================


async def orm_delete_user_archives(user_id: int) -> bool:
    """
    Видаляє всі збережені списки користувача та їх файли.
    """
    try:
        async with async_session() as session:
            # Отримуємо всі списки для видалення файлів
            result = await session.execute(
                select(SavedList).where(SavedList.user_id == user_id)
            )
            lists = result.scalars().all()

            # Видаляємо файли
            for saved_list in lists:
                if saved_list.file_path and os.path.exists(saved_list.file_path):
                    try:
                        os.remove(saved_list.file_path)
                        logger.info("Видалено файл: %s", saved_list.file_path)
                    except Exception as file_error:
                        logger.warning(
                            "Не вдалося видалити файл %s: %s",
                            saved_list.file_path,
                            file_error,
                        )

            # Видаляємо записи з БД
            await session.execute(delete(SavedList).where(SavedList.user_id == user_id))
            await session.commit()

            logger.info("Видалено всі архіви для user_id %s", user_id)
            return True

    except Exception as e:
        logger.error(
            "Помилка видалення архівів user_id %s: %s", user_id, e, exc_info=True
        )
        return False


async def orm_delete_saved_list(list_id: int) -> bool:
    """
    Видаляє конкретний збережений список та його файл.
    """
    try:
        async with async_session() as session:
            # Отримуємо список для видалення файлу
            result = await session.execute(
                select(SavedList).where(SavedList.id == list_id)
            )
            saved_list = result.scalar_one_or_none()

            if not saved_list:
                logger.warning("Список ID %s не знайдено", list_id)
                return False

            # Видаляємо файл
            if saved_list.file_path and os.path.exists(saved_list.file_path):
                try:
                    os.remove(saved_list.file_path)
                    logger.info("Видалено файл: %s", saved_list.file_path)
                except Exception as file_error:
                    logger.warning(
                        "Не вдалося видалити файл %s: %s",
                        saved_list.file_path,
                        file_error,
                    )

            # Видаляємо запис з БД (каскадно видаляться і items)
            await session.execute(delete(SavedList).where(SavedList.id == list_id))
            await session.commit()

            logger.info("Видалено список ID %s", list_id)
            return True

    except Exception as e:
        logger.error("Помилка видалення списку ID %s: %s", list_id, e, exc_info=True)
        return False


# ==============================================================================
# 📦 СТВОРЕННЯ ZIP АРХІВУ
# ==============================================================================


async def orm_pack_user_files_to_zip(user_id: int) -> Optional[str]:
    """
    Пакує всі файли користувача в один ZIP архів.
    Повертає шлях до створеного ZIP файлу або None при помилці.
    """
    try:
        # Отримуємо всі списки користувача
        saved_lists = await orm_get_user_lists_archive(user_id)

        if not saved_lists:
            logger.info("Користувач %s не має архівів для пакування", user_id)
            return None

        # Створюємо ZIP архів
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"user_{user_id}_archive_{timestamp}.zip"
        zip_path = os.path.join(ARCHIVES_PATH, zip_filename)

        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            files_added = 0

            for saved_list in saved_lists:
                if saved_list.file_path and os.path.exists(saved_list.file_path):
                    # Додаємо файл до архіву з оригінальною назвою
                    arcname = os.path.basename(saved_list.file_path)
                    zipf.write(saved_list.file_path, arcname)
                    files_added += 1
                    logger.debug("Додано до архіву: %s", arcname)

            if files_added == 0:
                # Якщо жодного файлу не додано, видаляємо ZIP
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                logger.warning(
                    "Не знайдено файлів для архівування user_id %s", user_id
                )
                return None

        logger.info(
            "Створено архів для user_id %s: %s (%s файлів)",
            user_id,
            zip_filename,
            files_added,
        )
        return zip_path

    except Exception as e:
        logger.error(
            "Помилка створення архіву для user_id %s: %s", user_id, e, exc_info=True
        )
        return None


# ==============================================================================
# 🧹 ОЧИСТКА СТАРИХ АРХІВІВ
# ==============================================================================


async def orm_cleanup_old_archives(days: int = 30) -> int:
    """
    Видаляє архіви старше вказаної кількості днів.
    Повертає кількість видалених записів.
    """
    try:
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days)

        async with async_session() as session:
            # Отримуємо старі списки
            result = await session.execute(
                select(SavedList).where(SavedList.created_at < cutoff_date)
            )
            old_lists = result.scalars().all()

            deleted_count = 0

            for saved_list in old_lists:
                # Видаляємо файл
                if saved_list.file_path and os.path.exists(saved_list.file_path):
                    try:
                        os.remove(saved_list.file_path)
                    except Exception as file_error:
                        logger.warning(
                            "Не вдалося видалити файл %s: %s",
                            saved_list.file_path,
                            file_error,
                        )

                # Видаляємо запис
                await session.execute(
                    delete(SavedList).where(SavedList.id == saved_list.id)
                )
                deleted_count += 1

            await session.commit()

            logger.info("Очищено старих архівів: %s (старше %s днів)", deleted_count, days)
            return deleted_count

    except Exception as e:
        logger.error("Помилка очищення старих архівів: %s", e, exc_info=True)
        return 0


# ==============================================================================
# 📊 СТАТИСТИКА АРХІВІВ
# ==============================================================================


async def orm_get_archives_stats() -> dict:
    """
    Повертає статистику по архівах (для адміна).
    """
    try:
        async with async_session() as session:
            # Загальна кількість
            from sqlalchemy import func

            total_result = await session.execute(select(func.count(SavedList.id)))
            total_archives = total_result.scalar_one()

            # Унікальні користувачі
            users_result = await session.execute(
                select(func.count(func.distinct(SavedList.user_id)))
            )
            total_users = users_result.scalar_one()

            # Розмір директорії
            total_size = 0
            if os.path.exists(ARCHIVES_PATH):
                for filename in os.listdir(ARCHIVES_PATH):
                    filepath = os.path.join(ARCHIVES_PATH, filename)
                    if os.path.isfile(filepath):
                        total_size += os.path.getsize(filepath)

            return {
                "total_archives": total_archives,
                "total_users": total_users,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            }

    except Exception as e:
        logger.error("Помилка отримання статистики архівів: %s", e, exc_info=True)
        return {
            "total_archives": 0,
            "total_users": 0,
            "total_size_mb": 0,
        }
