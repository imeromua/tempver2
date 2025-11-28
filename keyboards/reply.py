# epicservice/keyboards/reply.py

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

# ==============================================================================
# 🔤 КОНСТАНТИ ТЕКСТІВ КНОПОК
# ==============================================================================

# --- Головне меню ---
BTN_MY_LIST = "📦 Мій список"
BTN_MY_ARCHIVES = "🗂 Мої архіви"
BTN_NEW_LIST = "🆕 Новий список"
BTN_ADMIN_PANEL = "👑 Адмін-панель"

# --- Підменю "Мій список" ---
BTN_EDIT_LIST = "✏️ Редагувати"
BTN_SAVE_LIST = "💾 Зберегти"
BTN_DELETE_LIST = "🗑 Видалити"

# --- Підменю "Архіви" ---
BTN_DOWNLOAD_ALL = "📥 Завантажити все"
BTN_DELETE_ALL_ARCHIVES = "🗑 Видалити все"

# --- Адмін-панель ---
BTN_IMPORT = "📥 Імпорт"
BTN_EXPORT_STOCK = "📤 Експорт залишків"
BTN_EXPORT_COLLECTED = "📋 Експорт зібраного"
BTN_IMPORT_COLLECTED = "📉 Імпорт зібраного"
BTN_USERS = "👥 Користувачі"
BTN_ALL_ARCHIVES = "🗄 Архіви всіх"
BTN_UTILITIES = "🛠 Утиліти"

# --- Утиліти ---
BTN_UTIL_BROADCAST = "📢 Розсилка"
BTN_UTIL_VALIDATOR = "✅ Валідатор"
BTN_UTIL_CONVERTER = "🔄 Конвертер"
BTN_UTIL_CLEAN_DB = "🧨 Очистити БД"

# --- Навігація ---
BTN_BACK = "🔙 Назад"
BTN_TO_MAIN_MENU = "🏠 Головне меню"

# --- Підтвердження ---
BTN_YES_CONFIRM = "✅ Так, підтверджую"
BTN_NO_CANCEL = "❌ Ні, скасувати"

# --- Вибір кількості ---
BTN_QTY_PLUS_1 = "+1"
BTN_QTY_PLUS_5 = "+5"
BTN_QTY_PLUS_10 = "+10"
BTN_QTY_MINUS_1 = "-1"
BTN_QTY_MINUS_5 = "-5"
BTN_QTY_MINUS_10 = "-10"
BTN_QTY_ADD_ALL = "✅ Додати все"
BTN_QTY_MANUAL = "✏️ Ввести вручну"
BTN_QTY_CONFIRM = "✅ Підтвердити"
BTN_QTY_CANCEL = "❌ Скасувати"


# ==============================================================================
# 🎹 ГЕНЕРАТОРИ КЛАВІАТУР
# ==============================================================================


def get_main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Головне меню користувача."""
    buttons = [
        [KeyboardButton(text=BTN_MY_LIST)],
        [KeyboardButton(text=BTN_MY_ARCHIVES)],
        [KeyboardButton(text=BTN_NEW_LIST)],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=BTN_ADMIN_PANEL)])

    return ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, input_field_placeholder="Оберіть дію"
    )


def get_my_list_submenu_kb() -> ReplyKeyboardMarkup:
    """Підменю для управління поточним списком."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_EDIT_LIST), KeyboardButton(text=BTN_SAVE_LIST)],
            [KeyboardButton(text=BTN_DELETE_LIST)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def get_archives_submenu_kb() -> ReplyKeyboardMarkup:
    """Підменю для роботи з архівами."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DOWNLOAD_ALL)],
            [KeyboardButton(text=BTN_DELETE_ALL_ARCHIVES)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def get_admin_menu_kb() -> ReplyKeyboardMarkup:
    """Головне меню адміністратора."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_IMPORT), KeyboardButton(text=BTN_EXPORT_STOCK)],
            [
                KeyboardButton(text=BTN_EXPORT_COLLECTED),
                KeyboardButton(text=BTN_IMPORT_COLLECTED),
            ],
            [KeyboardButton(text=BTN_USERS), KeyboardButton(text=BTN_ALL_ARCHIVES)],
            [KeyboardButton(text=BTN_UTILITIES)],
            [KeyboardButton(text=BTN_TO_MAIN_MENU)],
        ],
        resize_keyboard=True,
    )


def get_utilities_menu_kb() -> ReplyKeyboardMarkup:
    """Меню утиліт для адміна."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_UTIL_BROADCAST)],
            [KeyboardButton(text=BTN_UTIL_VALIDATOR)],
            [KeyboardButton(text=BTN_UTIL_CONVERTER)],
            [KeyboardButton(text=BTN_UTIL_CLEAN_DB)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def get_confirmation_kb() -> ReplyKeyboardMarkup:
    """Клавіатура підтвердження дії (замість inline)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_YES_CONFIRM),
                KeyboardButton(text=BTN_NO_CANCEL),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_quantity_selection_kb(current_qty: int = 1) -> ReplyKeyboardMarkup:
    """Клавіатура для вибору кількості товару."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_QTY_MINUS_10),
                KeyboardButton(text=BTN_QTY_MINUS_5),
                KeyboardButton(text=BTN_QTY_MINUS_1),
            ],
            [KeyboardButton(text=f"📦 Кількість: {current_qty}")],
            [
                KeyboardButton(text=BTN_QTY_PLUS_1),
                KeyboardButton(text=BTN_QTY_PLUS_5),
                KeyboardButton(text=BTN_QTY_PLUS_10),
            ],
            [
                KeyboardButton(text=BTN_QTY_ADD_ALL),
                KeyboardButton(text=BTN_QTY_MANUAL),
            ],
            [
                KeyboardButton(text=BTN_QTY_CONFIRM),
                KeyboardButton(text=BTN_QTY_CANCEL),
            ],
        ],
        resize_keyboard=True,
    )


def get_list_editing_kb() -> ReplyKeyboardMarkup:
    """Клавіатура для режиму редагування списку."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Завершити редагування")],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )
