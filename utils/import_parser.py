# epicservice/utils/import_parser.py

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class ImportParser:
    """
    Клас для розбору файлів імпорту (Excel, ODS) з валідацією та нормалізацією.
    """

    # Словник синонімів для колонок
    COLUMN_ALIASES = {
        "department": ["в", "відділ", "dep", "department"],
        "group": ["г", "група", "group"],
        "article": ["а", "арт", "артикул", "код", "code", "sku"],
        "name": ["н", "назва", "найменування", "name", "title"],
        "qty": ["к", "кількість", "зал", "залишок", "qty", "quantity"],
        "months": ["м", "місяців", "без руху", "months"],
        "sum": ["с", "сума", "sum", "total"],
    }

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df: Optional[pd.DataFrame] = None
        self.validation_errors: List[str] = []

    def load_file(self) -> bool:
        """Завантажує файл у DataFrame залежно від розширення."""
        try:
            if self.file_path.endswith(".ods"):
                self.df = pd.read_excel(self.file_path, engine="odfpy")
            else:
                self.df = pd.read_excel(self.file_path)

            # Приводимо назви колонок до нижнього регістру та стрінгів
            self.df.columns = [str(col).lower().strip() for col in self.df.columns]
            return True
        except Exception as e:
            logger.error(f"Помилка читання файлу {self.file_path}: {e}")
            self.validation_errors.append(f"Не вдалося прочитати файл: {str(e)}")
            return False

    def _map_columns(self) -> Dict[str, str]:
        """Визначає відповідність колонок файлу до внутрішніх назв."""
        mapping = {}
        file_columns = set(self.df.columns)

        for internal_name, aliases in self.COLUMN_ALIASES.items():
            found = False
            for alias in aliases:
                if alias in file_columns:
                    mapping[internal_name] = alias
                    found = True
                    break
            # Якщо не знайшли обов'язкові колонки
            if not found and internal_name in ["department", "qty"]:
                # Артикул і Назва можуть бути разом, тому їх тут не перевіряємо жорстко поки що
                pass
        return mapping

    def _clean_numeric(self, val: Any) -> float:
        """Очищує числові значення (замінює коми, прибирає пробіли)."""
        if pd.isna(val):
            return 0.0
        s_val = str(val).replace(",", ".").replace("\xa0", "").strip()
        # Залишаємо тільки цифри, крапку і мінус
        s_val = re.sub(r"[^\d.-]", "", s_val)
        try:
            return float(s_val)
        except ValueError:
            return 0.0

    def parse_data(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Головний метод парсингу.
        Повертає: (список валідних товарів, список помилок)
        """
        if self.df is None:
            return [], self.validation_errors

        col_map = self._map_columns()

        # Перевірка критичних колонок
        if "qty" not in col_map:
            return [], ["Не знайдено колонку 'Кількість' (к, qty, залишок)."]

        # Визначаємо, чи є окремі колонки Артикул та Назва
        has_article_col = "article" in col_map
        has_name_col = "name" in col_map

        # Якщо немає ані Артикулу, ані Назви — біда
        if not has_article_col and not has_name_col:
            return [], ["Не знайдено колонок 'Артикул' або 'Назва'."]

        parsed_items = []

        for idx, row in self.df.iterrows():
            row_num = idx + 2  # Для відповідності Excel (1-header)

            # --- 1. Витягуємо Артикул і Назву ---
            raw_article = row.get(col_map.get("article")) if has_article_col else None
            raw_name = row.get(col_map.get("name")) if has_name_col else None

            final_article = None
            final_name = None

            # Логіка розділення "Артикул - Назва"
            if raw_article and pd.notna(raw_article):
                str_art = str(raw_article).strip()
                # Перевіряємо, чи це чистий артикул (8 цифр)
                if re.match(r"^\d{8}$", str_art):
                    final_article = str_art
                    final_name = str(raw_name).strip() if raw_name else "Без назви"
                else:
                    # Спробуємо розпарсити, якщо в колонці артикулу сміття або суміш
                    match = re.search(r"(\d{8})", str_art)
                    if match:
                        final_article = match.group(1)
                        final_name = str(raw_name).strip() if raw_name else str_art

            # Якщо артикул не знайдено в колонці артикулу, дивимось в назву
            if not final_article and raw_name and pd.notna(raw_name):
                str_name = str(raw_name).strip()
                # Шукаємо 8 цифр на початку або всередині
                match = re.search(r"^(\d{8})\s*[-–—\s]\s*(.*)", str_name)
                if match:
                    final_article = match.group(1)
                    final_name = match.group(2)
                else:
                    # Просто шукаємо будь-які 8 цифр
                    match_simple = re.search(r"(\d{8})", str_name)
                    if match_simple:
                        final_article = match_simple.group(1)
                        final_name = str_name  # Залишаємо як є

            # Валідація Артикулу
            if not final_article:
                # self.validation_errors.append(f"Рядок {row_num}: Не знайдено артикул (8 цифр).")
                continue  # Пропускаємо рядки без артикулу (це можуть бути підсумки)

            # --- 2. Числові дані ---
            try:
                qty_val = self._clean_numeric(row.get(col_map.get("qty")))

                sum_val = 0.0
                if "sum" in col_map:
                    sum_val = self._clean_numeric(row.get(col_map.get("sum")))

                # Розрахунок ціни
                price = 0.0
                if qty_val > 0 and sum_val > 0:
                    price = sum_val / qty_val
                elif qty_val == 0:
                    price = 0.0  # Якщо немає товару, ціна не важлива або стара

                months = 0
                if "months" in col_map:
                    months = int(self._clean_numeric(row.get(col_map.get("months"))))

                # Відділ
                dept = 0
                if "department" in col_map:
                    d_val = row.get(col_map.get("department"))
                    dept = int(self._clean_numeric(d_val))

                group = ""
                if "group" in col_map:
                    group = str(row.get(col_map.get("group"), "")).strip()

                parsed_items.append(
                    {
                        "артикул": final_article,
                        "назва": final_name,
                        "відділ": dept,
                        "група": group,
                        "кількість": str(
                            qty_val
                        ),  # Зберігаємо як стрінг для сумісності з БД
                        "сума_залишку": sum_val,
                        "ціна": price,
                        "місяці_без_руху": months,
                        "активний": True,
                    }
                )

            except Exception as e:
                self.validation_errors.append(
                    f"Рядок {row_num} (Арт {final_article}): Помилка даних - {e}"
                )

        return parsed_items, self.validation_errors
