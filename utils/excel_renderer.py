# epicservice/utils/excel_renderer.py

import os
from datetime import datetime

import pandas as pd

from config import ARCHIVES_PATH


def save_dataframe_to_excel(df: pd.DataFrame, filename_prefix: str) -> str | None:
    """
    Зберігає DataFrame у красивий Excel файл.
    Повертає шлях до файлу.
    """
    if df.empty:
        return None

    os.makedirs(ARCHIVES_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{filename_prefix}_{timestamp}.xlsx"
    file_path = os.path.join(ARCHIVES_PATH, filename)

    try:
        # Використовуємо writer для форматування
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")

            # Автоширина колонок
            worksheet = writer.sheets["Data"]
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                # Обмежуємо максимальну ширину
                max_len = min(max_len, 50)
                worksheet.column_dimensions[chr(65 + idx)].width = max_len

        return file_path
    except Exception as e:
        print(f"Excel generation error: {e}")
        return None
