# epicservice/database/orm/archives.py

import logging
import os
from typing import List, Optional

from sqlalchemy import delete, select

from database.engine import async_session
from database.models import SavedList, SavedListItem

logger = logging.getLogger(__name__)


# ==============================================================================
# 📋 ОТРИМАННЯ АРХІВІВ
# ==============================================================================


async def orm_get_user_lists_archive(user_id: int) -> List[SavedList]:
    """
    Отримує всі збережені списки користувача.
    Повертає список відсортований за датою (новіші спочатку).
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
            "Помилка отримання архівів user_id %s: %s", user_id, e, exc_info=True
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


async def orm_get_archive_by_id(archive_id: int) -> Optional[SavedList]:
    """
    Отримує конкретний архів за ID.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SavedList).where(SavedList.id == archive_id)
            )
            return result.scalar_one_or_none()

    except Exception as e:
        logger.error("Помилка отримання архіву ID %s: %s", archive_id, e, exc_info=True)
        return None


# ==============================================================================
# 🗑 ВИДАЛЕННЯ АРХІВІВ
# ==============================================================================


async def orm_delete_user_archives(user_id: int) -> bool:
    """
    Видаляє всі архіви користувача та файли.
    ВАЖЛИВО: Спочатку видаляє items, потім lists (FOREIGN KEY).
    """
    try:
        async with async_session() as session:
            # Спочатку отримуємо всі списки
            result = await session.execute(
                select(SavedList).where(SavedList.user_id == user_id)
            )
            saved_lists = result.scalars().all()

            # Видаляємо файли
            for saved_list in saved_lists:
                if saved_list.file_path and os.path.exists(saved_list.file_path):
                    try:
                        os.remove(saved_list.file_path)
                        logger.info("Видалено файл: %s", saved_list.file_path)
                    except Exception as file_error:
                        logger.warning(
                            "Помилка видалення файлу %s: %s",
                            saved_list.file_path,
                            file_error,
                        )

            # Видаляємо items (дочірні записи) СПОЧАТКУ
            for saved_list in saved_lists:
                await session.execute(
                    delete(SavedListItem).where(SavedListItem.list_id == saved_list.id)
                )

            # Тепер видаляємо lists
            await session.execute(delete(SavedList).where(SavedList.user_id == user_id))

            await session.commit()

            logger.info("Видалено архіви користувача %s", user_id)
            return True

    except Exception as e:
        logger.error(
            "Помилка видалення архівів user_id %s: %s", user_id, e, exc_info=True
        )
        return False


async def orm_delete_archive_by_id(archive_id: int) -> bool:
    """
    Видаляє конкретний архів за ID (включно з items та файлом).
    """
    try:
        async with async_session() as session:
            # Отримуємо архів
            result = await session.execute(
                select(SavedList).where(SavedList.id == archive_id)
            )
            archive = result.scalar_one_or_none()

            if not archive:
                logger.warning("Архів ID %s не знайдено", archive_id)
                return False

            # Видаляємо файл
            if archive.file_path and os.path.exists(archive.file_path):
                try:
                    os.remove(archive.file_path)
                    logger.info("Видалено файл: %s", archive.file_path)
                except Exception as file_error:
                    logger.warning(
                        "Помилка видалення файлу %s: %s", archive.file_path, file_error
                    )

            # Видаляємо items спочатку
            await session.execute(
                delete(SavedListItem).where(SavedListItem.list_id == archive_id)
            )

            # Видаляємо сам список
            await session.execute(delete(SavedList).where(SavedList.id == archive_id))

            await session.commit()

            logger.info("Видалено архів ID %s", archive_id)
            return True

    except Exception as e:
        logger.error("Помилка видалення архіву ID %s: %s", archive_id, e, exc_info=True)
        return False


# ==============================================================================
# 📦 ПАКУВАННЯ АРХІВІВ
# ==============================================================================


async def orm_pack_user_files_to_zip(user_id: int) -> Optional[str]:
    """
    Пакує всі файли користувача в ZIP архів.
    Повертає шлях до створеного ZIP файлу або None.
    """
    import zipfile
    from datetime import datetime

    from config import ARCHIVES_PATH

    try:
        archives = await orm_get_user_lists_archive(user_id)

        if not archives:
            logger.warning("Немає архівів для user_id %s", user_id)
            return None

        # Створюємо ZIP
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"archives_{user_id}_{timestamp}.zip"
        zip_path = os.path.join(ARCHIVES_PATH, zip_filename)

        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for archive in archives:
                if archive.file_path and os.path.exists(archive.file_path):
                    # Додаємо файл в ZIP з оригінальною назвою
                    zipf.write(archive.file_path, arcname=archive.file_name)

        logger.info("Створено ZIP архів для user_id %s: %s", user_id, zip_filename)
        return zip_path

    except Exception as e:
        logger.error("Помилка створення ZIP для user_id %s: %s", user_id, e, exc_info=True)
        return None
# ==============================================================================