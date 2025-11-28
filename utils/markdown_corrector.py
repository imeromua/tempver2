# epicservice/utils/markdown_corrector.py

import re
from typing import Optional


def escape_markdown(text: str, version: int = 1) -> str:
    """
    Екранує спеціальні символи Markdown.
    
    Args:
        text: Текст для екранування
        version: Версія Markdown (1 = старий, 2 = MarkdownV2)
    
    Returns:
        Екранований текст
    """
    if not isinstance(text, str):
        text = str(text)
    
    if version == 1:
        # Для parse_mode="Markdown" (старий)
        escape_chars = r"([*_`\[])"
        return re.sub(escape_chars, r"\\\1", text)
    else:
        # Для parse_mode="MarkdownV2" (новий)
        escape_chars = r"([_*\[\]()~`>#+\-=|{}.!])"
        return re.sub(escape_chars, r"\\\1", text)


def safe_markdown_text(text: str, allow_bold: bool = True, allow_italic: bool = True) -> str:
    """
    Безпечно форматує текст, зберігаючи базове форматування.
    
    Args:
        text: Вихідний текст
        allow_bold: Дозволити **жирний**
        allow_italic: Дозволити _курсив_
    
    Returns:
        Безпечний відформатований текст
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Екранує все окрім дозволених символів
    if allow_bold:
        # Зберігаємо ** для жирного
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        escaped_parts = []
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                # Зберігаємо жирний текст
                inner = part[2:-2]
                escaped_inner = escape_markdown(inner)
                escaped_parts.append(f"**{escaped_inner}**")
            else:
                escaped_parts.append(escape_markdown(part))
        text = ''.join(escaped_parts)
    else:
        text = escape_markdown(text)
    
    return text


def format_filename_safe(filename: str, max_length: int = 50) -> str:
    """
    Безпечно форматує назву файлу для відображення в Markdown.
    
    Args:
        filename: Назва файлу
        max_length: Максимальна довжина
    
    Returns:
        Безпечна назва файлу
    """
    # Обрізаємо якщо занадто довго
    if len(filename) > max_length:
        filename = filename[:max_length-3] + "..."
    
    # Екранує спецсимволи
    return escape_markdown(filename)


def format_number_safe(number: float, decimals: int = 2) -> str:
    """
    Безпечно форматує число для Markdown.
    
    Args:
        number: Число
        decimals: Кількість знаків після коми
    
    Returns:
        Відформатоване число
    """
    formatted = f"{number:.{decimals}f}"
    return escape_markdown(formatted)


def clean_text_for_markdown(text: str) -> str:
    """
    Очищає текст від проблемних символів перед відправкою.
    
    Args:
        text: Вихідний текст
    
    Returns:
        Очищений текст
    """
    if not text:
        return ""
    
    # Видаляє нульові байти
    text = text.replace('\x00', '')
    
    # Видаляє інші проблемні Unicode символи
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    
    # Замінює множинні пробіли на одинарні
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()
