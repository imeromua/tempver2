# epicservice/handlers/admin/import_handlers.py

import asyncio
import logging
import os
import shutil
from datetime import datetime

import pandas as pd
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, func

from config import ADMIN_IDS, ARCHIVES_PATH, BACKUP_DIR, DB_NAME, DB_TYPE
from database.engine import async_session
from database.models import Product, StockHistory
from keyboards.reply import get_admin_menu_kb
from keyboards.inline import get_yes_no_kb
from utils.import_processor import generate_import_preview, process_import_dataframe, read_excel_smart
from utils.markdown_corrector import format_filename_safe, escape_markdown

# 👇 Імпортуємо константи
from constants import DEPARTMENTS, DEPARTMENT_EMOJIS

logger = logging.getLogger(__name__)
router = Router()

class ImportStates(StatesGroup):
    waiting_for_file = State()
    confirming_preview = State()

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="import:cancel_early")]
    ])

# ==============================================================================
# 💾 АВТОМАТИЧНИЙ БЕКАП
# ==============================================================================

async def create_backup_before_import() -> bool:
    try:
        if DB_TYPE == "sqlite":
            os.makedirs(BACKUP_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"auto_backup_before_import_{timestamp}.db"
            backup_path = os.path.join(BACKUP_DIR, backup_filename)
            
            if os.path.exists(DB_NAME):
                shutil.copy2(DB_NAME, backup_path)
                logger.info("Автоматичний бекап створено: %s", backup_filename)
                return True
        return True
    except Exception as e:
        logger.error("Помилка створення бекапу: %s", e, exc_info=True)
        return False

# ==============================================================================
# 📥 ПОЧАТОК ІМПОРТУ
# ==============================================================================

async def proceed_with_import(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS: return

    await state.set_state(ImportStates.waiting_for_file)
    await message.answer(
        "📥 **Імпорт залишків**\n\n"
        "Надішліть Excel файл.\n"
        "• Артикули з файлу будуть оновлені/додані.\n"
        "• Артикули, яких НЕМАЄ в файлі, будуть деактивовані.\n\n"
        "👇 Для скасування натисніть кнопку:",
        reply_markup=get_cancel_kb()
    )

@router.callback_query(F.data == "import:cancel_early")
async def cancel_import_early(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Імпорт скасовано.", reply_markup=get_admin_menu_kb())
    await callback.answer()

# ==============================================================================
# 📄 ОБРОБКА ФАЙЛУ
# ==============================================================================

@router.message(ImportStates.waiting_for_file, F.document)
async def process_import_file_with_preview(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS: return

    document = message.document
    if not document.file_name.lower().endswith((".xlsx", ".xls", ".ods")):
        await message.answer("❌ Невірний формат файлу. Потрібен Excel.")
        return

    msg = await message.answer("⏳ Аналіз файлу (Smart Read)...")

    try:
        file = await bot.get_file(document.file_id)
        file_path = os.path.join(
            ARCHIVES_PATH,
            f"import_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        os.makedirs(ARCHIVES_PATH, exist_ok=True)
        await bot.download_file(file.file_path, file_path)

        loop = asyncio.get_running_loop()
        df, header_row_idx = await loop.run_in_executor(None, read_excel_smart, file_path)
        preview = generate_import_preview(df)

        await state.update_data(
            file_path=file_path,
            filename=document.file_name,
            total_rows=len(df),
            header_row_idx=header_row_idx
        )
        await state.set_state(ImportStates.confirming_preview)

        preview_text = (
            "👁 **ПРЕВʼЮ ІМПОРТУ**\n\n"
            f"📄 Файл: `{format_filename_safe(document.file_name)}`\n"
            f"📌 Заголовок знайдено на рядку: **{header_row_idx + 1}**\n"
            f"📊 Рядків даних: {preview.stats['total_rows']}\n"
            f"📋 Колонок: {preview.stats['columns_count']}\n\n"
            "🔍 **Розпізнані колонки:**\n"
        )

        for standard, detected in preview.columns_detected.items():
            emoji = "✅" if detected else "❌"
            std_names = {
                "department": "Відділ", "group": "Група", "article": "Артикул",
                "name": "Назва", "quantity": "Кількість", "sum": "Сума", "months_no_movement": "Без руху"
            }
            std_name = std_names.get(standard, standard)
            det_safe = escape_markdown(detected) if detected else 'не знайдено'
            preview_text += f"{emoji} {std_name}: {det_safe}\n"

        if preview.unknown_columns:
            preview_text += f"\n❓ Невідомі колонки: {len(preview.unknown_columns)} (будуть проігноровані)"

        preview_text += "\n\n⚠️ **Підтвердіть імпорт:**"

        await msg.delete()
        await message.answer(
            preview_text, 
            reply_markup=get_yes_no_kb("import"),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error("Помилка аналізу: %s", e, exc_info=True)
        try: await msg.delete()
        except: pass
        await message.answer(f"❌ Помилка читання файлу:\n{str(e)[:200]}")
        if "file_path" in locals() and os.path.exists(file_path): os.remove(file_path)
        await state.clear()

# ==============================================================================
# ✅ ПІДТВЕРДЖЕННЯ ТА ЗВІТ
# ==============================================================================

@router.callback_query(ImportStates.confirming_preview, F.data == "confirm:import:yes")
async def confirm_and_import(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    data = await state.get_data()
    file_path = data.get("file_path")
    filename = data.get("filename")
    
    if not file_path or not os.path.exists(file_path):
        await callback.message.answer("❌ Файл втрачено.")
        await state.clear()
        return

    msg = await callback.message.answer("💾 Бекап...")
    await create_backup_before_import()
    await msg.edit_text("📊 СИНХРОНІЗАЦІЯ БАЗИ...")
    
    try:
        loop = asyncio.get_running_loop()
        df, _ = await loop.run_in_executor(None, read_excel_smart, file_path)
        processed_df, validation = await loop.run_in_executor(
            None, process_import_dataframe, df, None
        )

        if not validation.is_valid:
            error_text = "\n".join(validation.errors[:10])
            await msg.edit_text(f"❌ Валідація не пройшла!\n\n{error_text}")
            if os.path.exists(file_path): os.remove(file_path)
            await state.clear()
            return

        # --- ІМПОРТ ---
        added, updated, deactivated, reactivated, zero_qty = 0, 0, 0, 0, 0
        file_articles = set()

        async with async_session() as session:
            # Отримуємо всі активні з БД
            res_all = await session.execute(select(Product.артикул).where(Product.активний == True))
            db_active_articles = set(res_all.scalars().all())

            for _, row in processed_df.iterrows():
                try:
                    art = str(row["артикул"])
                    file_articles.add(art)
                    qty_str = str(row["кількість"]).replace('.', ',')
                    price_float = float(row["ціна"]) if row["ціна"] is not None else 0.0
                    
                    try:
                        if float(str(row["кількість"]).replace(",", ".")) == 0: zero_qty += 1
                    except: pass

                    res = await session.execute(select(Product).where(Product.артикул == art))
                    existing = res.scalar_one_or_none()

                    if existing:
                        if not existing.активний:
                            existing.активний = True
                            reactivated += 1
                        
                        if existing.кількість != qty_str:
                            hist = StockHistory(
                                product_id=existing.id, articul=art,
                                old_quantity=existing.кількість, new_quantity=qty_str,
                                change_source="import"
                            )
                            session.add(hist)
                        
                        existing.кількість = qty_str
                        
                        # Часткове оновлення полів
                        if row["ціна"] is not None: existing.ціна = price_float
                        if row["сума_залишку"] is not None: existing.сума_залишку = float(row["сума_залишку"])
                        if row["місяці_без_руху"] is not None: existing.місяці_без_руху = int(row["місяці_без_руху"])
                        if row["назва"]: existing.назва = row["назва"]
                        if row["група"]: existing.група = row["група"]
                        if row["відділ"]: existing.відділ = row["відділ"]
                        
                        updated += 1
                    else:
                        new_p = Product(
                            артикул=art, назва=row["назва"] or "Без назви", 
                            відділ=row["відділ"] or 0, група=row["група"] or "",
                            кількість=qty_str, ціна=price_float,
                            сума_залишку=float(row["сума_залишку"]) if row["сума_залишку"] else 0.0,
                            місяці_без_руху=int(row["місяці_без_руху"]) if row["місяці_без_руху"] else 0,
                            відкладено=0, активний=True
                        )
                        session.add(new_p)
                        added += 1
                except: pass

            # Деактивація
            to_deact = db_active_articles - file_articles
            if to_deact:
                await session.execute(
                    update(Product).where(Product.артикул.in_(to_deact)).values(активний=False)
                )
                deactivated = len(to_deact)

            await session.commit()

            # --- 📊 ГЕНЕРАЦІЯ ЗВЕДЕНОГО ЗВІТУ ПО СКЛАДУ ---
            
            # Загальні показники
            total_items_query = await session.execute(
                select(func.count(Product.id)).where(Product.активний == True)
            )
            total_items = total_items_query.scalar_one()

            total_value_query = await session.execute(
                select(func.sum(Product.сума_залишку)).where(Product.активний == True)
            )
            total_value = total_value_query.scalar_one() or 0.0

            # По відділах
            dept_stats_query = await session.execute(
                select(
                    Product.відділ,
                    func.count(Product.id),
                    func.sum(Product.сума_залишку)
                )
                .where(Product.активний == True)
                .group_by(Product.відділ)
                .order_by(Product.відділ)
            )
            dept_stats = dept_stats_query.all()

        if os.path.exists(file_path): os.remove(file_path)

        # Форматування чисел
        def fmt(num):
            return f"{num:,.0f}".replace(",", " ")

        # --- СТВОРЕННЯ КРАСИВОГО ЗВІТУ ---
        report_text = (
            f"✅ **СИНХРОНІЗАЦІЮ ЗАВЕРШЕНО!**\n"
            f"📄 Файл: `{format_filename_safe(filename)}`\n\n"
            f"➕ Додано нових: {added}\n"
            f"🔄 Оновлено: {updated - reactivated}\n"
            f"♻️ Відновлено: {reactivated}\n"
            f"🔴 Деактивовано: {deactivated}\n"
            f"⚠️ Нульових: {zero_qty}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **СТАН СКЛАДУ**\n\n"
            f"Всього товарів: **{fmt(total_items)}** (активні)\n"
            f"Загальна вартість: **{fmt(total_value)} грн**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📍 **ПО ВІДДІЛАХ:**\n\n"
        )

        for dept_code, count, value in dept_stats:
            val = value or 0
            # Отримуємо назву та емодзі з констант
            dept_name = DEPARTMENTS.get(dept_code, str(dept_code))
            emoji = DEPARTMENT_EMOJIS.get(dept_code, "📦")
            
            # Якщо назва довга, обрізаємо або скорочуємо для краси
            if len(dept_name) > 20: dept_name = dept_name[:19] + "…"

            report_text += f"{emoji} **{dept_name}**\n   └ {count} арт. | **{fmt(val)} грн**\n"

        report_text += "━━━━━━━━━━━━━━━━━━━━━━"

        await msg.edit_text(report_text)
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error("Import error: %s", e, exc_info=True)
        await msg.delete()
        await callback.message.answer(f"❌ Помилка: {e}")
        if os.path.exists(file_path): os.remove(file_path)
        await state.clear()
        await callback.answer()

@router.callback_query(ImportStates.confirming_preview, F.data == "confirm:import:no")
async def cancel_import(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    path = data.get("file_path")
    if path and os.path.exists(path): os.remove(path)
    
    await callback.message.delete()
    await callback.message.answer("❌ Імпорт скасовано.", reply_markup=get_admin_menu_kb())
    await state.clear()
    await callback.answer()

@router.message(ImportStates.waiting_for_file)
async def invalid_import_file(message: Message):
    await message.answer("❌ Надішліть Excel файл або натисніть Скасувати.")

@router.message(F.text == "📤 Завантажити шаблон")
async def download_import_template(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Функція шаблону.")