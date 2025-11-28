# epicservice/database/orm/__init__.py

"""
Модуль ORM запитів для роботи з базою даних.
Експортує всі функції для зручного імпорту.
"""

# --- Аналітика ---
from .analytics import (
    orm_get_all_collected_items_sync,
    orm_get_department_stats,
    orm_get_top_products,
    orm_get_user_activity_stats,
)

# --- Архіви ---
from .archives import (
    orm_delete_archive_by_id,     # ✅ Додано (було пропущено)
    orm_delete_user_archives,
    orm_get_all_archives,
    orm_get_archive_by_id,        # ✅ Додано (було пропущено)
    orm_get_user_lists_archive,
    orm_pack_user_files_to_zip,
    # orm_cleanup_old_archives,   # ❌ Видалено (не існує в archives.py)
    # orm_delete_saved_list,      # ❌ Видалено (невірне ім'я, замінено на orm_delete_archive_by_id)
    # orm_get_archives_stats,     # ❌ Видалено (не існує в archives.py)
    # orm_get_saved_list_items,   # ❌ Видалено (не існує в archives.py)
)

# --- Товари ---
from .products import (
    get_available_quantity,
    orm_deactivate_product,
    orm_get_all_products,
    orm_get_product_by_article,
    orm_get_product_by_id,
    orm_get_products_count,
    orm_get_total_stock_value,
    orm_search_products_by_department,
    orm_search_products_fuzzy,
    orm_update_product_quantity,
    orm_update_product_reserved,
    validate_product_quantity,
)

# --- Тимчасові списки ---
from .temp_lists import (
    orm_add_item_to_temp_list,
    orm_clear_temp_list,
    orm_delete_item_from_temp_list,
    orm_get_temp_list,
    orm_get_temp_list_department,
    orm_get_temp_list_item,
    orm_get_temp_list_summary,
    orm_get_total_temp_reservation_for_product,
    orm_update_item_quantity,
)

# --- Користувачі ---
from .users import orm_add_user, orm_get_user

__all__ = [
    # Користувачі
    "orm_add_user",
    "orm_get_user",
    # Товари
    "orm_get_product_by_id",
    "orm_get_product_by_article",
    "orm_get_all_products",
    "orm_search_products_fuzzy",
    "orm_search_products_by_department",
    "orm_update_product_quantity",
    "orm_update_product_reserved",
    "orm_deactivate_product",
    "orm_get_products_count",
    "orm_get_total_stock_value",
    "validate_product_quantity",
    "get_available_quantity",
    # Тимчасові списки
    "orm_get_temp_list",
    "orm_get_temp_list_department",
    "orm_get_temp_list_item",
    "orm_add_item_to_temp_list",
    "orm_update_item_quantity",
    "orm_delete_item_from_temp_list",
    "orm_clear_temp_list",
    "orm_get_total_temp_reservation_for_product",
    "orm_get_temp_list_summary",
    # Архіви
    "orm_get_user_lists_archive",
    "orm_get_all_archives",
    "orm_get_archive_by_id",      # ✅
    "orm_delete_user_archives",
    "orm_delete_archive_by_id",   # ✅
    "orm_pack_user_files_to_zip",
    # Аналітика
    "orm_get_all_collected_items_sync",
    "orm_get_top_products",
    "orm_get_department_stats",
    "orm_get_user_activity_stats",
]