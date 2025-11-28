# epicservice/utils/import_processor.py

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ==============================================================================
# 📋 СЛОВНИК КОЛОНОК
# ==============================================================================

COLUMN_MAPPING = {
    "department": [
        "в",
        "відділ",
        "code",
        "department",
        "dept",
        "отдел",
        "категорія",
        "category",
    ],
    "group": [
        "г",
        "група",
        "group",
        "fg1_name",
        "підгрупа",
        "группа",
        "subgroup",
    ],
    "article": [
        "а",
        "артикул",
        "article",
        "articul",
        "код",
        "code_product",
        "product_code",
    ],
    "name": [
        "н",
        "назва",
        "название",
        "name",
        "product",
        "товар",
        "найменування",
        "articul_name",
    ],
    "quantity": [
        "к",
        "кількість",
        "quantity",
        "qty",
        "залишок",
        "остаток",
        "залишок (кількість)",
        "залишок, к-ть",
        "остаток (количество)",
    ],
    "sum": [
        "с",
        "сума",
        "sum",
        "сумма",
        "залишок, сума",
        "total",
        "сума залишку",
    ],
    "months_no_movement": [
        "м",
        "місяці без руху",
        "місяців без руху",
        "без руху",
        "months",
        "no_movement",
    ],
}


@dataclass
class ImportValidation:
    """Результат валідації імпорту."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    total_rows: int
    valid_rows: int


@dataclass
class ImportPreview:
    """Превʼю для підтвердження імпорту."""

    columns_detected: Dict[str, str]
    sample_rows: pd.DataFrame
    stats: Dict[str, any]


# ==============================================================================
# 🔍 РОЗПІЗНАВАННЯ КОЛОНОК
# ==============================================================================


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Автоматично визначає назви колонок за словником.
    
    Returns:
        dict: {стандартна_назва: фактична_назва_в_df}
    """
    detected = {}
    df_columns_lower = {col: col for col in df.columns}
    df_columns_normalized = {col.lower().strip(): col for col in df.columns}

    for standard_name, variations in COLUMN_MAPPING.items():
        found = None

        for variation in variations:
            variation_lower = variation.lower()

            # Точний збіг
            if variation_lower in df_columns_normalized:
                found = df_columns_normalized[variation_lower]
                break

            # Часткове входження
            for col_name, original_col in df_columns_normalized.items():
                if variation_lower in col_name or col_name in variation_lower:
                    found = original_col
                    break

            if found:
                break

        detected[standard_name] = found

    logger.info("Розпізнані колонки: %s", detected)
    return detected


# ==============================================================================
# 🔨 РОЗДІЛЕННЯ АРТИКУЛУ ВІД НАЗВИ
# ==============================================================================


def extract_article_and_name(combined_text: str) -> Tuple[str, str]:
    """
    Розділяє артикул та назву з одного рядка.
    
    Формати:
    - "12345678 - Назва товару"
    - "12345678 Назва товару"
    - "12345678-Назва товару"
    
    Returns:
        (артикул, назва)
    """
    if not combined_text or pd.isna(combined_text):
        return "", ""

    text = str(combined_text).strip()

    # Шукаємо 8-значний артикул на початку
    patterns = [
        r"^(\d{8})\s*-\s*(.+)$",  # "12345678 - Назва"
        r"^(\d{8})\s+(.+)$",  # "12345678 Назва"
        r"^(\d{8})-(.+)$",  # "12345678-Назва"
    ]

    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            article = match.group(1)
            name = match.group(2).strip()
            return article, name

    # Якщо не знайшли - повертаємо як є
    return "", text


# ==============================================================================
# ✅ ВАЛІДАЦІЯ ДАНИХ
# ==============================================================================


def validate_article(article: str) -> Tuple[bool, Optional[str]]:
    """Перевіряє артикул."""
    if not article:
        return False, "Артикул порожній"

    article_str = str(article).strip()

    if not article_str.isdigit():
        return False, "Артикул має містити тільки цифри"

    if len(article_str) != 8:
        return False, f"Артикул має бути 8 цифр (знайдено: {len(article_str)})"

    return True, None


def validate_quantity(quantity: any) -> Tuple[bool, Optional[str]]:
    """Перевіряє кількість."""
    try:
        qty = float(str(quantity).replace(",", "."))

        if qty < 0:
            return False, "Кількість не може бути від'ємною"

        if qty > 100000:
            return False, f"Підозріло велика кількість: {qty}"

        return True, None

    except (ValueError, TypeError):
        return False, "Невірний формат кількості"


def validate_price(price: float, article: str = "") -> Tuple[bool, Optional[str]]:
    """Перевіряє ціну."""
    if price < 0:
        return False, "Ціна не може бути від'ємною"

    if price == 0:
        return False, "Ціна дорівнює 0"

    if price > 1000000:
        return False, f"Підозріло висока ціна: {price}"

    return True, None


# ==============================================================================
# 📊 ОБРОБКА DATAFRAME
# ==============================================================================


def process_import_dataframe(
    df: pd.DataFrame, column_map: Optional[Dict[str, str]] = None
) -> Tuple[pd.DataFrame, ImportValidation]:
    """
    Обробляє DataFrame для імпорту.
    
    Args:
        df: Вихідний DataFrame
        column_map: Мапінг колонок (якщо None - автовизначення)
    
    Returns:
        (оброблений_df, валідація)
    """
    errors = []
    warnings = []

    # Автовизначення колонок
    if column_map is None:
        column_map = detect_columns(df)

    # Перевіряємо обов'язкові колонки
    required = ["department", "group", "quantity"]
    missing = [r for r in required if not column_map.get(r)]

    if missing:
        return df, ImportValidation(
            is_valid=False,
            errors=[f"Відсутні обов'язкові колонки: {', '.join(missing)}"],
            warnings=[],
            total_rows=len(df),
            valid_rows=0,
        )

    # Створюємо стандартизований DataFrame
    processed_rows = []

    for idx, row in df.iterrows():
        try:
            # Відділ
            department = int(row[column_map["department"]])

            # Група
            group = str(row[column_map["group"]]).strip()

            # Артикул та назва
            if column_map.get("article") and column_map.get("name"):
                # Окремі колонки
                article = str(row[column_map["article"]]).strip()
                name = str(row[column_map["name"]]).strip()
            elif column_map.get("name"):
                # Разом в одній колонці
                combined = row[column_map["name"]]
                article, name = extract_article_and_name(combined)
            else:
                errors.append(f"Рядок {idx + 2}: не вдалося визначити артикул/назву")
                continue

            # Валідація артикулу
            is_valid, error = validate_article(article)
            if not is_valid:
                errors.append(f"Рядок {idx + 2}: {error}")
                continue

            # Кількість
            quantity_raw = row[column_map["quantity"]]
            quantity = float(str(quantity_raw).replace(",", "."))

            is_valid, error = validate_quantity(quantity)
            if not is_valid:
                errors.append(f"Рядок {idx + 2}: {error}")
                continue

            # Сума та ціна
            price = 0.0
            total_sum = 0.0

            if column_map.get("sum"):
                total_sum = float(str(row[column_map["sum"]]).replace(",", "."))
                if quantity > 0:
                    price = round(total_sum / quantity, 2)

                # Валідація ціни
                is_valid, error = validate_price(price, article)
                if not is_valid:
                    warnings.append(f"Рядок {idx + 2} [{article}]: {error}")

            # Місяці без руху
            months_no_movement = 0
            if column_map.get("months_no_movement"):
                try:
                    months_no_movement = int(row[column_map["months_no_movement"]])
                except (ValueError, TypeError):
                    months_no_movement = 0

            # Додаємо оброблений рядок
            processed_rows.append({
                "артикул": article,
                "назва": name,
                "відділ": department,
                "група": group,
                "кількість": str(quantity).replace(".", ","),
                "ціна": price,
                "сума_залишку": total_sum,
                "місяці_без_руху": months_no_movement,
            })

        except Exception as row_error:
            errors.append(f"Рядок {idx + 2}: {str(row_error)}")
            logger.error("Помилка обробки рядка %s: %s", idx + 2, row_error)

    processed_df = pd.DataFrame(processed_rows)

    validation = ImportValidation(
        is_valid=len(processed_rows) > 0,
        errors=errors,
        warnings=warnings,
        total_rows=len(df),
        valid_rows=len(processed_rows),
    )

    return processed_df, validation


# ==============================================================================
# 👁 ПРЕВЬЮ ІМПОРТУ
# ==============================================================================


def generate_import_preview(df: pd.DataFrame) -> ImportPreview:
    """Генерує превʼю для підтвердження імпорту."""
    column_map = detect_columns(df)

    # Беремо перші 5 рядків для превʼю
    sample = df.head(5)

    # Статистика
    stats = {
        "total_rows": len(df),
        "columns_count": len(df.columns),
        "has_article": bool(column_map.get("article") or column_map.get("name")),
        "has_quantity": bool(column_map.get("quantity")),
    }

    return ImportPreview(
        columns_detected=column_map, sample_rows=sample, stats=stats
    )
