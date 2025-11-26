# epicservice/keyboards/inline.py

from typing import Union
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.models import Product
from lexicon.lexicon import LEXICON

# --- Головні меню ---

def get_user_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_NEW_LIST, callback_data="main:new_list"),
         InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_MY_LIST, callback_data="main:my_list")],
        [InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_ARCHIVE, callback_data="main:archive")]
    ])

def get_admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_NEW_LIST, callback_data="main:new_list"),
         InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_MY_LIST, callback_data="main:my_list")],
        [InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_ADMIN_PANEL, callback_data="admin:main")],
        [InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_ARCHIVE, callback_data="main:archive")]
    ])

# === НОВЕ ГОЛОВНЕ МЕНЮ АДМІНА ===
def get_admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.ADMIN_BTN_IMPORTS, callback_data="admin:import_products")],
        [InlineKeyboardButton(text=LEXICON.ADMIN_BTN_EXPORTS, callback_data="admin:exports_menu")], # Нове
        [InlineKeyboardButton(text=LEXICON.ADMIN_BTN_REPORTS, callback_data="admin:reports_menu")], # Нове
        [InlineKeyboardButton(text=LEXICON.ADMIN_BTN_BACKUPS, callback_data="admin:backups_menu")], # Нове
        [InlineKeyboardButton(text=LEXICON.ADMIN_BTN_USERS, callback_data="admin:users_menu")],     # Нове
        [InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_MAIN_MENU, callback_data="main:back")]
    ])

# === МЕНЮ БЕКАПІВ ===
def get_backups_menu_kb(backups: list) -> InlineKeyboardMarkup:
    kb = []
    # Кнопки дій
    kb.append([InlineKeyboardButton(text=LEXICON.BACKUP_BTN_CREATE, callback_data="backup:create")])
    kb.append([InlineKeyboardButton(text=LEXICON.BACKUP_BTN_CLEANUP, callback_data="backup:cleanup")])
    
    # Список файлів (для завантаження)
    for b in backups[:5]: # Показуємо тільки 5 останніх, щоб не забити екран
        btn_text = f"📥 {b['filename']} ({b['size']})"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"backup:download:{b['filename']}")])
        
    kb.append([InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_ADMIN_PANEL, callback_data="admin:main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# === МЕНЮ ЕКСПОРТІВ ===
def get_exports_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.EXPORT_BTN_DB_FULL, callback_data="export:db_full")],
        [InlineKeyboardButton(text=LEXICON.EXPORT_BTN_ACTIVE, callback_data="export:db_active")],
        [InlineKeyboardButton(text=LEXICON.EXPORT_BTN_NO_MOVE, callback_data="export:no_move")],
        [InlineKeyboardButton(text=LEXICON.EXPORT_BTN_COLLECTED, callback_data="export:collected")],
        [InlineKeyboardButton(text=LEXICON.EXPORT_BTN_HISTORY, callback_data="export:history")],
        [InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_ADMIN_PANEL, callback_data="admin:main")]
    ])

# === МЕНЮ ЗВІТІВ ===
def get_reports_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.REPORT_BTN_PRODUCTS, callback_data="report:products")],
        [InlineKeyboardButton(text=LEXICON.REPORT_BTN_DEPTS, callback_data="report:depts")],
        [InlineKeyboardButton(text=LEXICON.REPORT_BTN_USERS, callback_data="report:users")],
        [InlineKeyboardButton(text=LEXICON.REPORT_BTN_FINANCE, callback_data="report:finance")],
        [InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_ADMIN_PANEL, callback_data="admin:main")]
    ])

# --- Інші існуючі клавіатури (залишаємо як є) ---
def get_import_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON.BUTTON_CONFIRM_IMPORT, callback_data="import:confirm")],
        [InlineKeyboardButton(text=LEXICON.BUTTON_CANCEL_IMPORT, callback_data="import:cancel")]
    ])

def get_search_results_kb(products: list) -> InlineKeyboardMarkup:
    keyboard = []
    for product in products:
        name = product.назва[:30] + "..." if len(product.назва) > 30 else product.назва
        keyboard.append([InlineKeyboardButton(text=f"{product.артикул} | {name}", callback_data=f"product:{product.id}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_product_actions_kb(product_id: int, available_quantity: Union[int, float], search_query: str | None = None) -> InlineKeyboardMarkup:
    qty_text = f"{available_quantity:.2f}" if isinstance(available_quantity, float) else str(available_quantity)
    actions = []
    if available_quantity > 0:
        actions.append(InlineKeyboardButton(text=f"✅ Додати все ({qty_text})", callback_data=f"add_all:{product_id}:{available_quantity}"))
    actions.append(InlineKeyboardButton(text="📝 Ввести кількість", callback_data=f"select_quantity:{product_id}"))
    
    nav = []
    if search_query:
        nav.append(InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_SEARCH, callback_data="back_to_results"))
    nav.append(InlineKeyboardButton(text=LEXICON.INLINE_BUTTON_MY_LIST, callback_data="main:my_list"))
    nav.append(InlineKeyboardButton(text=LEXICON.BUTTON_BACK_TO_MAIN_MENU, callback_data="main:back"))
    return InlineKeyboardMarkup(inline_keyboard=[actions, nav] if not actions else [actions, nav])

def get_quantity_selector_kb(product_id: int, current_qty: int, max_qty: int) -> InlineKeyboardMarkup:
    # (Код без змін)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️", callback_data=f"product:{product_id}")]
    ]) 

def get_admin_lock_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=LEXICON.BUTTON_NOTIFY_USERS, callback_data=f"lock:notify:{action}"),
        InlineKeyboardButton(text=LEXICON.BUTTON_FORCE_SAVE, callback_data=f"lock:force_save:{action}")
    ]])

def get_notify_confirmation_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=LEXICON.BUTTON_YES_NOTIFY, callback_data="notify_confirm:yes"),
        InlineKeyboardButton(text=LEXICON.BUTTON_NO_NOTIFY, callback_data="notify_confirm:no"),
    ]])

def get_my_list_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Редагувати", callback_data="edit_list:start")]])

def get_list_for_editing_kb(temp_list: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="main:my_list")]])

def get_confirmation_kb(confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Так", callback_data=confirm_callback),
        InlineKeyboardButton(text="Ні", callback_data=cancel_callback),
    ]])

def get_users_with_archives_kb(users: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin:main")]])

def get_archive_kb(user_id: int, is_admin_view: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="main:back")]])