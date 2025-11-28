# epicservice/handlers/admin/archive_handlers.py

import logging
import os
import zipfile
from datetime import datetime
from typing import Optional

from aiogram import F, Router

from config import ADMIN_IDS, ARCHIVES_PATH
from database.orm import orm_get_all_files_for_user

# Налаштовуємо логер
logger = logging.getLogger(__name__)

# Створюємо роутер (навіть якщо він поки порожній, це потрібно для bot.py)
router = Router()
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


async def _pack_user_files_to_zip(user_id: int) -> Optional[str]:
    """
    Пакує всі збережені файли користувача в один ZIP-архів.
    Використовується в menu_navigation.py
    """
    try:
        file_paths = await orm_get_all_files_for_user(user_id)
        if not file_paths:
            return None

        os.makedirs(ARCHIVES_PATH, exist_ok=True)
        zip_filename = (
            f"user_{user_id}_archive_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        )
        zip_path = os.path.join(ARCHIVES_PATH, zip_filename)

        with zipfile.ZipFile(zip_path, "w") as zipf:
            for file_path in file_paths:
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))

        return zip_path
    except Exception as e:
        logger.error(
            "Помилка створення ZIP-архіву для користувача %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return None


# Старі хендлери для перегляду архівів (admin:user_archives) видалені,
# оскільки зараз цей розділ на реконструкції в menu_navigation.
