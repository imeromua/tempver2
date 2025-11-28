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
from sqlalchemy import select, update

from config import ADMIN_IDS, ARCHIVES_PATH, BACKUP_DIR, DB_NAME, DB_TYPE
from database.engine import async_session
from database.models import Product, StockHistory
from keyboards.reply import get_admin_menu_kb
from keyboards.inline import get_yes_no_kb
# Імпортуємо необхідні інструменти
from utils.import_processor import generate_import_preview, process_import_dataframe, read_excel_smart
from utils.markdown_corrector import format_filename_safe, escape_markdown

logger = logging.getLogger(__name__)
router = Router()

class ImportStates(StatesGroup):
    waiting_for_file = State()
    confirming_preview = State()

# --- Локальна клавіатура скасування ---
def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="import:cancel_early")]
    ])

# ==============================================================================
# 💾 АВТОМАТИЧНИЙ БЕКАП
# ==============================================================================

async def create_backup_before_import() -> bool:
    """Створює автоматичний бекап перед імпортом (тільки для SQLite)."""
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
        return True  # Для Postgres бекап налаштовується засобами СКБД
    except Exception as e:
        logger.error("Помилка створення бекапу: %s", e, exc_info=True)
        return False

# ==============================================================================
# 📥 ПОЧАТОК ІМПОРТУ
# ==============================================================================

async def proceed_with_import(message: Message, state: FSMContext, bot: Bot):
    """Запускає процес імпорту залишків."""
    if message.from_user.id not in ADMIN_IDS:
        return

    await state.set_state(ImportStates.waiting_for_file)
    
    # Оновлений текст згідно з вашим запитом
    await message.answer(
        "📥 **Імпорт залишків**\n\n"
        "Надішліть Excel файл.\n"
        "• Артикули з файлу будуть оновлені/додані.\n"
        "• Артикули, яких НЕМАЄ в файлі, будуть деактивовані (але не видалені).\n\n"
        "👇 Для скасування натисніть кнопку:",
        reply_markup=get_cancel_kb()
    )

@router.callback_query(F.data == "import:cancel_early")
async def cancel_import_early(callback: CallbackQuery, state: FSMContext):
    """Скасування на етапі очікування файлу."""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Імпорт скасовано.", reply_markup=get_admin_menu_kb())
    await callback.answer()

# ==============================================================================
# 📄 ОБРОБКА ФАЙЛУ З ПРЕВʼЮ
# ==============================================================================

@router.message(ImportStates.waiting_for_file, F.document)
async def process_import_file_with_preview(message: Message, state: FSMContext, bot: Bot):
    """Обробляє файл та показує превʼю з Inline-кнопками."""
    if message.from_user.id not in ADMIN_IDS:
        return

    document = message.document
    # Перевірка розширення
    if not document.file_name.lower().endswith((".xlsx", ".xls", ".ods")):
        await message.answer("❌ Невірний формат файлу. Потрібен Excel (.xlsx, .xls, .ods).")
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
        
        # ВИКОРИСТОВУЄМО SMART READ
        # Ця функція сама знайде рядок із заголовками і пропустить сміття
        df, header_row_idx = await loop.run_in_executor(None, read_excel_smart, file_path)

        preview = generate_import_preview(df)

        await state.update_data(
            file_path=file_path,
            filename=document.file_name,
            total_rows=len(df),
            header_row_idx=header_row_idx
        )
        await state.set_state(ImportStates.confirming_preview)

        # Формуємо текст превʼю
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
            # Переклад для відображення
            std_names = {
                "department": "Відділ", "group": "Група", "article": "Артикул",
                "name": "Назва", "quantity": "Кількість", "sum": "Сума", "months_no_movement": "Без руху"
            }
            std_name = std_names.get(standard, standard)
            
            # Екрануємо назву колонки, бо там можуть бути спецсимволи
            det_safe = escape_markdown(detected) if detected else 'не знайдено'
            preview_text += f"{emoji} {std_name}: {det_safe}\n"

        if preview.unknown_columns:
            preview_text += f"\n❓ Невідомі колонки: {len(preview.unknown_columns)} (будуть проігноровані)"

        preview_text += "\n\n⚠️ **Підтвердіть імпорт:**"

        await msg.delete()
        # Відправляємо INLINE клавіатуру для підтвердження
        await message.answer(
            preview_text, 
            reply_markup=get_yes_no_kb("import"), # confirm:import:yes/no
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error("Помилка аналізу файлу: %s", e, exc_info=True)
        try: await msg.delete()
        except: pass
        
        await message.answer(f"❌ Помилка читання файлу:\n{str(e)[:200]}")
        
        if "file_path" in locals() and os.path.exists(file_path):
            os.remove(file_path)
        await state.clear()

# ==============================================================================
# ✅ ПІДТВЕРДЖЕННЯ (CALLBACK)
# ==============================================================================

@router.callback_query(ImportStates.confirming_preview, F.data == "confirm:import:yes")
async def confirm_and_import(callback: CallbackQuery, state: FSMContext):
    """Виконує імпорт після натискання Inline-кнопки."""
    await callback.message.delete()
    
    data = await state.get_data()
    file_path = data.get("file_path")
    filename = data.get("filename")
    header_row_idx = data.get("header_row_idx", 0)

    if not file_path or not os.path.exists(file_path):
        await callback.message.answer("❌ Файл втрачено. Почніть імпорт заново.")
        await state.clear()
        await callback.answer()
        return

    msg = await callback.message.answer("💾 Створення бекапу...")
    await create_backup_before_import()
    await msg.edit_text("📊 СИНХРОНІЗАЦІЯ БАЗИ...")
    
    try:
        loop = asyncio.get_running_loop()
        
        # Читаємо файл знову, використовуючи Smart Read
        df, _ = await loop.run_in_executor(None, read_excel_smart, file_path)
        
        processed_df, validation = await loop.run_in_executor(
            None, process_import_dataframe, df, None
        )

        if not validation.is_valid:
            error_text = f"❌ Валідація не пройдена!\nПомилок: {len(validation.errors)}\n\n"
            error_text += "\n".join(validation.errors[:10])
            await msg.edit_text(error_text)
            if os.path.exists(file_path): os.remove(file_path)
            await state.clear()
            return

        # --- СТАТИСТИКА ---
        added = 0
        updated = 0
        deactivated = 0
        reactivated = 0
        zero_qty_count = 0
        
        file_articles = set()

        async with async_session() as session:
            # 1. Отримуємо всі поточні активні артикули з БД для порівняння
            result_all = await session.execute(select(Product.артикул).where(Product.активний == True))
            db_active_articles = set(result_all.scalars().all())

            # 2. Проходимо по файлу
            for _, row in processed_df.iterrows():
                try:
                    article = str(row["артикул"])
                    file_articles.add(article)

                    # Типізація
                    qty_str = str(row["кількість"]).replace('.', ',')
                    
                    try:
                        if float(str(row["кількість"]).replace(",", ".")) == 0:
                            zero_qty_count += 1
                    except: pass

                    price_float = float(row["ціна"]) if row["ціна"] is not None else 0.0
                    
                    # Пошук в БД
                    result = await session.execute(select(Product).where(Product.артикул == article))
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        # --- ЛОГІКА ОНОВЛЕННЯ ---
                        
                        # 1. Відновлення (Reactivation)
                        if not existing.активний:
                            existing.активний = True
                            reactivated += 1
                        
                        # 2. Часткове оновлення (Partial Update)
                        if existing.кількість != qty_str:
                            hist = StockHistory(
                                product_id=existing.id, articul=article,
                                old_quantity=existing.кількість, new_quantity=qty_str,
                                change_source="import"
                            )
                            session.add(hist)
                        
                        existing.кількість = qty_str
                        
                        # Оновлюємо, якщо дані є у файлі
                        if row["ціна"] is not None: existing.ціна = price_float
                        if row["сума_залишку"] is not None: existing.сума_залишку = float(row["сума_залишку"])
                        if row["місяці_без_руху"] is not None: existing.місяці_без_руху = int(row["місяці_без_руху"])

                        if row["назва"]: existing.назва = row["назва"]
                        if row["група"]: existing.група = row["група"]
                        if row["відділ"]: existing.відділ = row["відділ"]
                        
                        updated += 1
                        
                    else:
                        # --- ДОДАВАННЯ НОВОГО ---
                        new_p = Product(
                            артикул=article, назва=row["назва"] or "Без назви", 
                            відділ=row["відділ"] or 0, група=row["група"] or "",
                            кількість=qty_str, 
                            ціна=price_float,
                            сума_залишку=row["сума_залишку"] or 0.0,
                            місяці_без_руху=row["місяці_без_руху"] or 0,
                            відкладено=0, активний=True
                        )
                        session.add(new_p)
                        added += 1
                        
                except Exception as row_e:
                    logger.error(f"Row error: {row_e}")

            # 3. ДЕАКТИВАЦІЯ (Ті, що були в БД активні, але їх немає в файлі)
            to_deactivate = db_active_articles - file_articles
            
            if to_deactivate:
                await session.execute(
                    update(Product)
                    .where(Product.артикул.in_(to_deactivate))
                    .values(активний=False)
                )
                deactivated = len(to_deactivate)
                logger.info(f"Деактивовано {deactivated} товарів.")

            await session.commit()

        if os.path.exists(file_path):
            os.remove(file_path)

        # --- ФІНАЛЬНИЙ ЗВІТ ---
        report_text = (
            f"✅ **СИНХРОНІЗАЦІЮ ЗАВЕРШЕНО!**\n"
            f"📄 Файл: `{format_filename_safe(filename)}`\n\n"
            f"➕ Додано нових: **{added}**\n"
            f"🔄 Оновлено: **{updated - reactivated}**\n"
            f"♻️ Відновлено: **{reactivated}**\n"
            f"🔴 Деактивовано (немає в файлі): **{deactivated}**\n"
            f"⚠️ Товарів з нульовим залишком: **{zero_qty_count}**"
        )
        
        await msg.edit_text(report_text)
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error("Критична помилка імпорту: %s", e, exc_info=True)
        await msg.delete()
        await callback.message.answer(f"❌ Помилка імпорту:\n{str(e)[:200]}")
        
        if os.path.exists(file_path):
            os.remove(file_path)
        await state.clear()
        await callback.answer()

@router.callback_query(ImportStates.confirming_preview, F.data == "confirm:import:no")
async def cancel_import(callback: CallbackQuery, state: FSMContext):
    """Скасовує імпорт."""
    data = await state.get_data()
    file_path = data.get("file_path")
    
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    await callback.message.delete()
    await callback.message.answer("❌ Імпорт скасовано.", reply_markup=get_admin_menu_kb())
    await state.clear()
    await callback.answer()

# ==============================================================================
# 🚫 ОБРОБКА ПОМИЛОК ТА ДОДАТКОВІ ФУНКЦІЇ
# ==============================================================================

@router.message(ImportStates.waiting_for_file)
async def invalid_import_file(message: Message):
    """Обробляє невірний тип повідомлення."""
    await message.answer(
        "❌ Будь ласка, надішліть Excel файл (.xlsx, .xls, .ods)\n"
        "Або натисніть кнопку Скасувати."
    )

@router.message(F.text == "📤 Завантажити шаблон")
async def download_import_template(message: Message):
    """Генерує та відправляє шаблон для імпорту."""
    if message.from_user.id not in ADMIN_IDS: return

    try:
        template_data = {
            "в": [610, 310],
            "г": ["Драй фуд", "Побутова техніка"],
            "а": ["61602145", "31062294"],
            "н": ["Вино", "Машина пральна"],
            "м": [0, 3],
            "к": ["10", "2"],
            "с": [4500.50, 15000.00],
        }
        df = pd.DataFrame(template_data)
        
        template_path = os.path.join(ARCHIVES_PATH, "import_template.xlsx")
        os.makedirs(ARCHIVES_PATH, exist_ok=True)
        df.to_excel(template_path, index=False, engine="openpyxl")

        await message.answer_document(
            FSInputFile(template_path),
            caption="📋 Шаблон для імпорту (короткі назви колонок)"
        )
        os.remove(template_path)

    except Exception as e:
        logger.error("Template error: %s", e)
        await message.answer("❌ Помилка створення шаблону.")