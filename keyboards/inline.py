# epicservice/keyboards/inline.py

"""
ЗАСТАРІЛИЙ МОДУЛЬ!

Цей файл більше не використовується в проекті.
Всі inline клавіатури були замінені на Reply клавіатури (keyboards/reply.py).

Міграція завершена:
- ✅ Головне меню -> Reply
- ✅ Адмін-панель -> Reply
- ✅ Додавання товарів -> Reply
- ✅ Редагування списку -> Reply
- ✅ Підтвердження дій -> Reply

Якщо цей файл імпортується в коді - видаліть ці імпорти.

Дата застаріння: 28.11.2025
"""

# Для зворотної сумісності залишаємо порожні заглушки
# Видаліть цей файл повністю після перевірки, що ніде не імпортується


def get_confirmation_kb(*args, **kwargs):
    """ЗАСТАРІЛО: Використовуйте keyboards.reply.get_confirmation_kb()"""
    raise NotImplementedError(
        "Inline клавіатури більше не підтримуються. "
        "Використовуйте keyboards.reply.get_confirmation_kb()"
    )


def get_quantity_selector_kb(*args, **kwargs):
    """ЗАСТАРІЛО: Використовуйте keyboards.reply.get_quantity_selection_kb()"""
    raise NotImplementedError(
        "Inline клавіатури більше не підтримуються. "
        "Використовуйте keyboards.reply.get_quantity_selection_kb()"
    )


def get_list_editing_kb(*args, **kwargs):
    """ЗАСТАРІЛО: Використовуйте keyboards.reply.get_list_editing_kb()"""
    raise NotImplementedError(
        "Inline клавіатури більше не підтримуються. "
        "Використовуйте keyboards.reply.get_list_editing_kb()"
    )