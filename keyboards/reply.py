# epicservice/keyboards/reply.py

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# --- Тексти кнопок ---
BTN_NEW_LIST = "🆕 Новий список"
BTN_MY_LIST = "📋 Мій список"
BTN_MY_ARCHIVES = "🗂 Мої архіви"
BTN_ADMIN_PANEL = "👑 Адмінка"

# Підменю "Мій список"
BTN_SAVE_LIST = "💾 Зберегти"
BTN_DELETE_LIST = "🗑 Видалити список"
BTN_EDIT_LIST = "✏️ Редагування"
BTN_BACK = "🔙 Назад"

# Підменю "Мої архіви"
BTN_DOWNLOAD_ALL = "📦 Скачати все архівом"
BTN_DELETE_ALL_ARCHIVES = "🗑 Видалити все"

# Адмінка
BTN_IMPORT = "📥 Імпорт залишків"
BTN_EXPORT_STOCK = "📤 Експорт складу"
BTN_IMPORT_COLLECTED = "📉 Імпорт зібраного (мінус)"  # Перейменував для ясності
BTN_EXPORT_COLLECTED = "📋 Експорт зібраного"

BTN_USERS = "👥 Користувачі"
BTN_ALL_ARCHIVES = "🗄 Архіви юзерів"
BTN_UTILITIES = "🛠 Утиліти"  # Нова назва
BTN_TO_MAIN_MENU = "🔙 Головне меню"

# Утиліти
BTN_UTIL_BROADCAST = "📢 Розсилка"
BTN_UTIL_VALIDATOR = "✅ Валідатор таблиць"
BTN_UTIL_CLEAN_DB = "🧨 Повна очистка БД"
BTN_UTIL_CONVERTER = "🪄 Конвертер таблиць"
BTN_UTIL_MAPPING = "🗺 Ручний мапінг"


def get_main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_NEW_LIST))
    builder.row(KeyboardButton(text=BTN_MY_LIST), KeyboardButton(text=BTN_MY_ARCHIVES))

    if is_admin:
        builder.row(KeyboardButton(text=BTN_ADMIN_PANEL))

    return builder.as_markup(resize_keyboard=True)


def get_my_list_submenu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=BTN_SAVE_LIST), KeyboardButton(text=BTN_DELETE_LIST)
    )
    builder.row(KeyboardButton(text=BTN_EDIT_LIST))
    builder.row(KeyboardButton(text=BTN_BACK))
    return builder.as_markup(resize_keyboard=True)


def get_archives_submenu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_DOWNLOAD_ALL))
    builder.row(KeyboardButton(text=BTN_DELETE_ALL_ARCHIVES))
    builder.row(KeyboardButton(text=BTN_BACK))
    return builder.as_markup(resize_keyboard=True)


def get_admin_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    # Ряд 1: Основні операції з товаром
    builder.row(KeyboardButton(text=BTN_IMPORT), KeyboardButton(text=BTN_EXPORT_STOCK))
    # Ряд 2: Робота зі зібраним
    builder.row(
        KeyboardButton(text=BTN_IMPORT_COLLECTED),
        KeyboardButton(text=BTN_EXPORT_COLLECTED),
    )
    # Ряд 3: Люди, архіви, утиліти
    builder.row(KeyboardButton(text=BTN_USERS), KeyboardButton(text=BTN_ALL_ARCHIVES))
    builder.row(KeyboardButton(text=BTN_UTILITIES))
    # Ряд 4: Вихід
    builder.row(KeyboardButton(text=BTN_TO_MAIN_MENU))
    return builder.as_markup(resize_keyboard=True)


def get_utilities_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=BTN_UTIL_BROADCAST), KeyboardButton(text=BTN_UTIL_VALIDATOR)
    )
    builder.row(
        KeyboardButton(text=BTN_UTIL_CONVERTER), KeyboardButton(text=BTN_UTIL_MAPPING)
    )
    builder.row(KeyboardButton(text=BTN_UTIL_CLEAN_DB))
    builder.row(KeyboardButton(text=BTN_BACK))  # Повертає в меню адміна
    return builder.as_markup(resize_keyboard=True)
