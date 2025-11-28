# epicservice/utils/backup_utils.py

import logging
import os
import shutil
from datetime import datetime

from config import BACKUP_DIR, DB_NAME, DB_TYPE

logger = logging.getLogger(__name__)


def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)


def create_backup(prefix: str = "manual") -> str | None:
    """
    Створює бекап бази даних (тільки SQLite).
    prefix: 'manual' або 'auto'
    Повертає ім'я створеного файлу.
    """
    if DB_TYPE != "sqlite" or not os.path.exists(DB_NAME):
        return None

    ensure_backup_dir()
    # Додаємо секунди для унікальності
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Використовуємо basename, щоб уникнути шляхів у назві файлу
    filename = f"backup_{prefix}_{timestamp}_{os.path.basename(DB_NAME)}"
    dest_path = os.path.join(BACKUP_DIR, filename)

    try:
        shutil.copy2(DB_NAME, dest_path)
        return filename
    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        return None


def get_backups_list() -> list[dict]:
    """
    Повертає список словників з інформацією про бекапи.
    Сортує від нових до старих.
    """
    ensure_backup_dir()
    backups = []

    if not os.path.exists(BACKUP_DIR):
        return []

    for f in os.listdir(BACKUP_DIR):
        # --- ВИПРАВЛЕННЯ: Прибрали перевірку f.endswith(".db") ---
        # Тепер бот побачить ваші файли epicservice_db
        if f.startswith("backup_"):
            path = os.path.join(BACKUP_DIR, f)
            try:
                stat = os.stat(path)

                # Визначаємо тип (Auto/Manual)
                b_type = "🤖 Авто" if "_auto_" in f else "👤 Ручний"

                # Форматуємо дату
                dt = datetime.fromtimestamp(stat.st_mtime)
                date_str = dt.strftime("%d.%m.%Y %H:%M:%S")

                # Форматуємо розмір (MB)
                size_mb = stat.st_size / (1024 * 1024)

                backups.append(
                    {
                        "filename": f,
                        "path": path,
                        "date": date_str,
                        "timestamp": stat.st_mtime,
                        "size": f"{size_mb:.2f} МБ",
                        "type": b_type,
                    }
                )
            except OSError as e:
                logger.warning(f"Skipping file {f}: {e}")

    # Сортуємо: найновіші зверху
    return sorted(backups, key=lambda x: x["timestamp"], reverse=True)


def delete_old_backups(keep_last: int = 5) -> int:
    """Видаляє старі бекапи, залишаючи N останніх."""
    backups = get_backups_list()
    if len(backups) <= keep_last:
        return 0

    deleted_count = 0
    for b in backups[keep_last:]:
        try:
            os.remove(b["path"])
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete {b['filename']}: {e}")

    return deleted_count
