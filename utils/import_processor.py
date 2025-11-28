# epicservice/utils/import_processor.py

import logging
import re
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

logger = logging.getLogger(__name__)
MAPPING_FILE = "column_mapping.json"

# ==============================================================================
# 📋 СЛОВНИК КОЛОНОК (БАЗОВИЙ)
# ==============================================================================

DEFAULT_MAPPING = {
    "department": ["в", "відділ", "code", "department", "dept", "отдел", "категорія", "код відділу"],
    "group": ["г", "група", "group", "fg1_name", "підгрупа", "группа", "subgroup"],
    "article": ["а", "артикул", "article", "articul", "код", "code_product", "product_code"],
    "name": ["н", "назва", "название", "name", "product", "товар", "найменування", "articul_name"],
    "quantity": ["к", "кількість", "quantity", "qty", "залишок", "остаток", "залишок, к-ть", "к-ть"],
    "sum": ["с", "сума", "sum", "сумма", "залишок, сума", "total", "сума залишку"],
    "months_no_movement": ["м", "місяці без руху", "місяців без руху", "без руху", "months", "no_movement"]
}

# Список колонок, які ми вирішили ігнорувати назавжди
IGNORED_COLUMNS = ["тц", "period_type", "war_status", "simple_name", "к-ть арт"]

@dataclass
class ImportValidation:
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    total_rows: int
    valid_rows: int

@dataclass
class ImportPreview:
    columns_detected: Dict[str, str]
    unknown_columns: List[str]
    sample_rows: pd.DataFrame
    stats: Dict[str, Any]
    header_row_index: int

# ==============================================================================
# 🧠 РОЗУМНЕ ЧИТАННЯ (SMART READ)
# ==============================================================================

def read_excel_smart(file_path: str) -> Tuple[pd.DataFrame, int]:
    """
    Знаходить заголовок, пропускаючи сміття на початку файлу.
    """
    try:
        # Читаємо перші 20 рядків
        preview_df = pd.read_excel(file_path, header=None, nrows=20)
    except Exception as e:
        logger.error(f"Read error: {e}")
        return pd.read_excel(file_path), 0

    best_idx = 0
    max_matches = 0
    
    # Збираємо всі відомі нам слова
    keywords = set()
    for aliases in DEFAULT_MAPPING.values():
        for a in aliases: keywords.add(a.lower())
    
    # Шукаємо рядок з найбільшою кількістю знайомих слів
    for idx, row in preview_df.iterrows():
        matches = 0
        row_vals = [str(v).lower().strip() for v in row.values if pd.notna(v)]
        
        for v in row_vals:
            if v in keywords: matches += 1
        
        if matches > max_matches:
            max_matches = matches
            best_idx = idx

    logger.info(f"Smart Read: Header found at row {best_idx} (matches: {max_matches})")

    # Читаємо начисто
    df = pd.read_excel(file_path, header=best_idx)
    # Очищаємо назви колонок
    df.columns = df.columns.astype(str).str.strip()
    return df, best_idx

# ==============================================================================
# 💾 МЕНЕДЖЕР МАПІНГУ (JSON)
# ==============================================================================

def load_custom_mapping() -> Dict[str, List[str]]:
    """Завантажує збережені налаштування користувача."""
    if not os.path.exists(MAPPING_FILE):
        return {}
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Config load error: {e}")
        return {}

def update_saved_mapping(internal_key: str, file_column_name: str):
    """
    Зберігає нове правило: file_column_name -> internal_key.
    """
    current = load_custom_mapping()
    col_lower = file_column_name.lower().strip()
    
    if internal_key == 'IGNORE':
        ignored = current.get('IGNORE', [])
        if col_lower not in ignored:
            ignored.append(col_lower)
            current['IGNORE'] = ignored
    else:
        aliases = current.get(internal_key, [])
        if col_lower not in aliases:
            aliases.append(col_lower)
            current[internal_key] = aliases

    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    logger.info(f"Mapping saved: {col_lower} -> {internal_key}")

# ==============================================================================
# 🔍 ДЕТЕКЦІЯ КОЛОНОК
# ==============================================================================

def detect_columns(df: pd.DataFrame) -> Tuple[Dict[str, str], List[str]]:
    """
    Мапить колонки файлу на внутрішні назви.
    """
    detected = {}
    df_cols_lower = {str(c).lower().strip(): c for c in df.columns}
    
    custom_map = load_custom_mapping()
    
    combined_mapping = DEFAULT_MAPPING.copy()
    for k, v in custom_map.items():
        if k != 'IGNORE':
            combined_mapping[k] = combined_mapping.get(k, []) + v
    
    ignored_list = IGNORED_COLUMNS + custom_map.get('IGNORE', [])

    used_file_cols = set()
    
    for key, aliases in combined_mapping.items():
        found = None
        for alias in aliases:
            if alias in df_cols_lower:
                found = df_cols_lower[alias]
                used_file_cols.add(found)
                break
        detected[key] = found

    unknown = []
    for col in df.columns:
        c_low = str(col).lower().strip()
        if (col not in used_file_cols and 
            c_low not in ignored_list and 
            not str(col).startswith("Unnamed")):
            unknown.append(str(col))

    return detected, unknown

# ==============================================================================
# 🔨 ВАЛІДАЦІЯ ТА ЕКСТРАКЦІЯ
# ==============================================================================

def extract_article_and_name(text: str) -> Tuple[str, str]:
    """
    Розділяє '12345678 - Назва товару' на артикул і назву.
    """
    if not text or pd.isna(text):
        return "", ""
    
    s = str(text).strip()
    
    # 🔥 ВИПРАВЛЕНО: Екранування дефісу [\s\-\–\—]
    m = re.match(r"^(\d{8})[\s\-\–\—]+(.+)$", s)
    if m:
        return m.group(1), m.group(2).strip()
        
    # Спроба 2: Просто пробіл
    m = re.match(r"^(\d{8})\s+(.+)$", s)
    if m:
        return m.group(1), m.group(2).strip()
        
    # Якщо не вдалося розділити - повертаємо як є (можливо артикул в іншій колонці)
    return "", s

def validate_article(val) -> Tuple[bool, Optional[str]]:
    s = str(val).strip()
    if not s: return False, "Пусто"
    if not s.isdigit(): return False, "Не цифри"
    if len(s) != 8: return False, "Не 8 цифр"
    return True, None

# ==============================================================================
# 📊 ОБРОБКА DATAFRAME
# ==============================================================================

def process_import_dataframe(df: pd.DataFrame, custom_map=None) -> Tuple[pd.DataFrame, ImportValidation]:
    """
    Перетворює вхідний DataFrame у стандартизований формат.
    """
    col_map, _ = detect_columns(df)
    if custom_map:
        col_map.update(custom_map)

    errors = []
    warnings = []
    rows = []
    
    # Перевірка мінімуму: повинна бути хоча б Кількість
    if not col_map.get("quantity"):
        return df, ImportValidation(
            False, ["Не знайдено колонку 'Кількість'"], [], len(df), 0
        )

    for idx, row in df.iterrows():
        rid = idx + 2
        try:
            art, name = "", ""
            
            # --- 1. АРТИКУЛ ТА НАЗВА ---
            # Варіант А: Є окремі колонки
            if col_map.get("article") and col_map.get("name"):
                art = str(row[col_map["article"]]).strip()
                name = str(row[col_map["name"]]).strip()
            
            # Варіант Б: Є тільки Назва (артикул всередині)
            elif col_map.get("name") and not col_map.get("article"):
                art, name = extract_article_and_name(row[col_map["name"]])
                
            # Варіант В: Є тільки Артикул
            elif col_map.get("article"):
                art = str(row[col_map["article"]]).strip()

            # Валідація артикулу
            valid, _ = validate_article(art)
            if not valid:
                # Пропускаємо рядки без валідного артикулу (підсумки, сміття)
                continue 

            # --- 2. КІЛЬКІСТЬ (Обов'язкове) ---
            qty_raw = str(row[col_map["quantity"]]).replace(",", ".").replace(" ", "").replace("\xa0", "")
            try:
                qty = float(qty_raw)
            except:
                errors.append(f"Ряд {rid} (Арт {art}): помилка кількості '{qty_raw}'")
                continue

            # --- 3. ІНШІ ПОЛЯ (Необов'язкові -> None) ---
            dept = None
            if col_map.get("department"):
                try: dept = int(float(str(row[col_map["department"]])))
                except: pass
            
            grp = None
            if col_map.get("group"):
                grp = str(row[col_map["group"]]).strip()

            sum_val = None
            price = None
            if col_map.get("sum"):
                try:
                    sum_val = float(str(row[col_map["sum"]]).replace(",", ".").replace(" ", "").replace("\xa0", ""))
                    if qty > 0:
                        price = round(sum_val / qty, 2)
                except: pass
            
            mnth = None
            if col_map.get("months_no_movement"):
                try: mnth = int(float(str(row[col_map["months_no_movement"]])))
                except: pass

            rows.append({
                "артикул": art,
                "назва": name,
                "відділ": dept,
                "група": grp,
                "кількість": qty,
                "ціна": price,
                "сума_залишку": sum_val,
                "місяці_без_руху": mnth
            })

        except Exception as e:
            errors.append(f"Ряд {rid}: {e}")

    processed_df = pd.DataFrame(rows)
    
    return processed_df, ImportValidation(
        is_valid=len(rows) > 0,
        errors=errors,
        warnings=warnings,
        total_rows=len(df),
        valid_rows=len(rows)
    )

def generate_import_preview(df: pd.DataFrame) -> ImportPreview:
    cmap, unk = detect_columns(df)
    return ImportPreview(
        columns_detected=cmap,
        unknown_columns=unk,
        sample_rows=df.head(3),
        stats={"total_rows": len(df), "columns_count": len(df.columns)},
        header_row_index=0
    )