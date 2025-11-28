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
from aiogram.types import FSInputFile, Message
from sqlalchemy import select

from config import ADMIN_IDS, ARCHIVES_PATH, BACKUP_DIR, DB_NAME, DB_TYPE
from database.engine import async_session
from database.models import Product, StockHistory
from keyboards.reply import get_admin_menu_kb, get_confirmation_kb
from utils.import_processor import generate_import_preview, process_import_dataframe
from utils.markdown_corrector import (
    clean_text_for_markdown,
    escape_markdown,
    format_filename_safe,
)

logger = logging.getLogger(__name__)
router = Router()


class ImportStates(StatesGroup):
    waiting_for_file = State()
    confirming_preview = State()
    manual_mapping = State()


# ==============================================================================
# 💾 АВТОМАТИЧНИЙ БЕКАП ПЕРЕД ІМПОРТОМ
# ==============================================================================


async def create_backup_before_import() -> bool:
    """Створює автоматичний бекап перед імпортом."""
    try:
        if DB_TYPE == "sqlite":
            os.makedirs(BACKUP_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"auto_backup_before_import_{timestamp}.db"
            backup_path = os.path.join(BACKUP_DIR, backup_filename)

            shutil.copy2(DB_NAME, backup_path)
            logger.info("Автоматичний бекап створено: %s", backup_filename)
            return True

        return True  # Для PostgreSQL бекап має бути налаштований окремо

    except Exception as e:
        logger.error("Помилка створення бекапу: %s", e, exc_info=True)
        return False


# ==============================================================================
# 📥 ПОЧАТОК ІМПОРТУ
# ==============================================================================


async def proceed_with_import(message: Message, state: FSMContext, bot: Bot):
    """Запускає процес імпорту залишків."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    await state.set_state(ImportStates.waiting_for_file)

    help_text = (
        "📥 Розумний імпорт залишків\n\n"
        "Надішліть Excel файл (.xlsx, .xls, .ods)\n\n"
        "Що вміє бот:\n"
        "• Автовизначення колонок\n"
        "• Розділення артикул + назва\n"
        "• Валідація даних\n"
        "• Бекап перед імпортом\n"
        "• Превʼю перед підтвердженням\n\n"
        "Підтримувані формати:\n"
        "• Короткі назви: в, г, а, н, м, к, с\n"
        "• Повні назви: Відділ, Група, Артикул\n"
        "• Комбіновані: артикул + назва в одній колонці\n\n"
        "Для скасування: /reset"
    )

    await message.answer(help_text, reply_markup=get_admin_menu_kb())


# ==============================================================================
# 📄 ОБРОБКА ФАЙЛУ З ПРЕВʼЮ
# ==============================================================================


@router.message(ImportStates.waiting_for_file, F.document)
async def process_import_file_with_preview(
    message: Message, state: FSMContext, bot: Bot
):
    """Обробляє файл та показує превʼю для підтвердження."""
    if message.from_user.id not in ADMIN_IDS:
        return

    document = message.document

    # Перевірка формату
    valid_extensions = (".xlsx", ".xls", ".ods")
    if not document.file_name.endswith(valid_extensions):
        await message.answer(
            f"❌ Невірний формат файлу.\n"
            f"Підтримуються: {', '.join(valid_extensions)}"
        )
        return

    msg = await message.answer("⏳ Аналіз файлу...")

    try:
        # Завантажуємо файл
        file = await bot.get_file(document.file_id)
        file_path = os.path.join(
            ARCHIVES_PATH,
            f"import_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        os.makedirs(ARCHIVES_PATH, exist_ok=True)

        await bot.download_file(file.file_path, file_path)

        # Читаємо Excel (в executor щоб не блокувати)
        loop = asyncio.get_running_loop()

        # Підтримка різних форматів
        if document.file_name.endswith(".ods"):
            df = await loop.run_in_executor(None, pd.read_excel, file_path, None, "odf")
        else:
            df = await loop.run_in_executor(None, pd.read_excel, file_path)

        # Генеруємо превʼю
        preview = generate_import_preview(df)

        # Зберігаємо в state
        await state.update_data(
            file_path=file_path,
            filename=document.file_name,
            total_rows=len(df),
        )
        await state.set_state(ImportStates.confirming_preview)

        # Форматуємо превʼю для відображення (БЕЗ MARKDOWN)
        preview_text = (
            "👁 ПРЕВʼЮ ІМПОРТУ\n\n"
            f"📄 Файл: {format_filename_safe(document.file_name)}\n"
            f"📊 Рядків: {preview.stats['total_rows']}\n"
            f"📋 Колонок: {preview.stats['columns_count']}\n\n"
            "🔍 Розпізнані колонки:\n"
        )

        for standard, detected in preview.columns_detected.items():
            if detected:
                emoji = "✅"
            else:
                emoji = "❌"

            standard_ua = {
                "department": "Відділ",
                "group": "Група",
                "article": "Артикул",
                "name": "Назва",
                "quantity": "Кількість",
                "sum": "Сума",
                "months_no_movement": "Без руху",
            }.get(standard, standard)

            detected_safe = escape_markdown(detected) if detected else "не знайдено"
            preview_text += f"{emoji} {standard_ua}: {detected_safe}\n"

        # Показуємо приклад даних
        preview_text += "\n📋 Перші 3 рядки:\n\n"
        sample_str = preview.sample_rows.head(3).to_string(index=False, max_colwidth=30)
        sample_str = clean_text_for_markdown(sample_str)
        preview_text += sample_str[:500]
        preview_text += "\n\n⚠️ Підтвердіть імпорт:"

        await msg.delete()
        # Відправляємо БЕЗ parse_mode для безпеки
        await message.answer(
            preview_text, reply_markup=get_confirmation_kb(), parse_mode=None
        )

    except Exception as e:
        logger.error("Помилка аналізу файлу: %s", e, exc_info=True)

        try:
            await msg.delete()
        except:
            pass

        error_msg = f"❌ Помилка читання файлу:\n{str(e)[:200]}"
        await message.answer(error_msg, reply_markup=get_admin_menu_kb())

        if "file_path" in locals() and os.path.exists(file_path):
            os.remove(file_path)

        await state.clear()


# ==============================================================================
# ✅ ПІДТВЕРДЖЕННЯ ТА ІМПОРТ
# ==============================================================================


@router.message(ImportStates.confirming_preview, F.text == "✅ Так, підтверджую")
async def confirm_and_import(message: Message, state: FSMContext, bot: Bot):
    """Підтверджує превʼю та виконує імпорт."""
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    file_path = data.get("file_path")
    filename = data.get("filename")
    total_rows = data.get("total_rows", 0)

    if not file_path or not os.path.exists(file_path):
        await message.answer("❌ Файл не знайдено. Почніть імпорт заново.")
        await state.clear()
        return

    # Створюємо бекап
    msg = await message.answer("💾 Створення бекапу...")
    backup_success = await create_backup_before_import()

    if not backup_success:
        await msg.delete()
        await message.answer(
            "⚠️ Не вдалося створити бекап!\nПродовжити імпорт без бекапу?",
            reply_markup=get_confirmation_kb(),
        )
        return

    try:
        await msg.delete()
        progress_msg = await message.answer(
            "📊 Імпорт даних...\n⏳ 0%", parse_mode=None
        )

        # Читаємо файл
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, pd.read_excel, file_path)

        # Обробляємо та валідуємо
        processed_df, validation = await loop.run_in_executor(
            None, process_import_dataframe, df, None
        )

        if not validation.is_valid:
            error_text = (
                f"❌ Валідація не пройдена!\n\n"
                f"Помилок: {len(validation.errors)}\n\n"
            )

            for error in validation.errors[:10]:
                error_text += f"• {error}\n"

            if len(validation.errors) > 10:
                error_text += f"\n... та ще {len(validation.errors) - 10} помилок"

            await progress_msg.delete()
            await message.answer(
                error_text, reply_markup=get_admin_menu_kb(), parse_mode=None
            )

            if os.path.exists(file_path):
                os.remove(file_path)

            await state.clear()
            return

        # Імпорт у БД
        added_count = 0
        updated_count = 0
        skipped_count = 0
        price_warnings = []

        total = len(processed_df)
        last_progress = 0

        async with async_session() as session:
            for idx, row in processed_df.iterrows():
                try:
                    article = row["артикул"]

                    # Оновлюємо прогрес кожні 10%
                    current_progress = int((idx / total) * 100)
                    if current_progress >= last_progress + 10:
                        last_progress = current_progress
                        try:
                            await progress_msg.edit_text(
                                f"📊 Імпорт даних...\n⏳ {current_progress}%",
                                parse_mode=None,
                            )
                        except Exception:
                            pass  # Ігноруємо помилки редагування

                    # Шукаємо існуючий товар
                    result = await session.execute(
                        select(Product).where(Product.артикул == article)
                    )
                    existing_product = result.scalar_one_or_none()

                    if existing_product:
                        # Перевірка зміни ціни >50%
                        if existing_product.ціна and row["ціна"] > 0:
                            old_price = existing_product.ціна
                            new_price = row["ціна"]
                            change_percent = abs(
                                (new_price - old_price) / old_price * 100
                            )

                            if change_percent > 50:
                                price_warnings.append(
                                    f"⚠️ {article}: ціна {old_price:.2f} → {new_price:.2f} ({change_percent:.0f}%)"
                                )

                        # Оновлюємо
                        old_quantity = existing_product.кількість
                        existing_product.назва = row["назва"]
                        existing_product.відділ = row["відділ"]
                        existing_product.група = row["група"]
                        existing_product.кількість = row["кількість"]
                        existing_product.ціна = row["ціна"]
                        existing_product.сума_залишку = row["сума_залишку"]
                        existing_product.місяці_без_руху = row["місяці_без_руху"]
                        existing_product.активний = True

                        # Історія
                        history = StockHistory(
                            product_id=existing_product.id,
                            articul=article,
                            old_quantity=old_quantity,
                            new_quantity=row["кількість"],
                            change_source="import",
                        )
                        session.add(history)
                        updated_count += 1
                    else:
                        # Створюємо новий
                        new_product = Product(
                            артикул=article,
                            назва=row["назва"],
                            відділ=row["відділ"],
                            група=row["група"],
                            кількість=row["кількість"],
                            ціна=row["ціна"],
                            сума_залишку=row["сума_залишку"],
                            місяці_без_руху=row["місяці_без_руху"],
                            відкладено=0,
                            активний=True,
                        )
                        session.add(new_product)
                        added_count += 1

                except Exception as row_error:
                    logger.error("Помилка імпорту рядка %s: %s", idx, row_error)
                    skipped_count += 1

            await session.commit()

        # Видаляємо тимчасовий файл
        if os.path.exists(file_path):
            os.remove(file_path)

        # Результат
        filename_safe = format_filename_safe(filename)
        result_text = (
            "✅ ІМПОРТ ЗАВЕРШЕНО!\n\n"
            f"📄 Файл: {filename_safe}\n"
            f"📊 Всього рядків: {total_rows}\n\n"
            f"➕ Додано нових: {added_count}\n"
            f"🔄 Оновлено: {updated_count}\n"
            f"⏭ Пропущено: {skipped_count}\n"
        )

        if validation.warnings:
            result_text += f"\n⚠️ Попереджень: {len(validation.warnings)}"

        if price_warnings:
            result_text += f"\n\n💰 Значні зміни цін ({len(price_warnings)}):\n"
            for warning in price_warnings[:5]:
                result_text += f"{warning}\n"
            if len(price_warnings) > 5:
                result_text += f"... та ще {len(price_warnings) - 5}"

        await progress_msg.delete()
        await message.answer(
            result_text, reply_markup=get_admin_menu_kb(), parse_mode=None
        )
        await state.clear()

        logger.info(
            "Імпорт завершено: %s додано, %s оновлено, %s пропущено",
            added_count,
            updated_count,
            skipped_count,
        )

    except Exception as e:
        logger.error("Критична помилка імпорту: %s", e, exc_info=True)

        try:
            await progress_msg.delete()
        except:
            pass

        error_msg = f"❌ Помилка імпорту:\n{str(e)[:200]}"
        await message.answer(error_msg, reply_markup=get_admin_menu_kb())

        if "file_path" in locals() and os.path.exists(file_path):
            os.remove(file_path)

        await state.clear()


@router.message(ImportStates.confirming_preview, F.text == "❌ Ні, скасувати")
async def cancel_import_preview(message: Message, state: FSMContext):
    """Скасовує імпорт після превʼю."""
    data = await state.get_data()
    file_path = data.get("file_path")

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    await state.clear()
    await message.answer("❌ Імпорт скасовано.", reply_markup=get_admin_menu_kb())


@router.message(ImportStates.waiting_for_file)
async def invalid_import_file(message: Message):
    """Обробляє невірний тип повідомлення."""
    await message.answer(
        "❌ Будь ласка, надішліть Excel файл (.xlsx, .xls, .ods)\n"
        "Або скасуйте командою /reset"
    )


# ==============================================================================
# 📤 ЕКСПОРТ ШАБЛОНУ
# ==============================================================================


@router.message(F.text == "📤 Завантажити шаблон")
async def download_import_template(message: Message):
    """Генерує та відправляє шаблон для імпорту."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас немає доступу до цієї функції.")
        return

    try:
        # Створюємо шаблон
        template_data = {
            "в": [610, 310, 70],
            "г": ["Драй фуд", "Велика побутова техніка", "Опалення"],
            "а": ["61602145", "31062294", "70204771"],
            "н": [
                "Вино Origin Wine Australia",
                "Машина пральна WHIRLPOOL",
                "Водонагрівач",
            ],
            "м": [0, 3, 1],
            "к": ["10", "2", "5"],
            "с": [4500.50, 15000.00, 8200.00],
        }

        df = pd.DataFrame(template_data)

        # Зберігаємо файл
        template_path = os.path.join(ARCHIVES_PATH, "import_template.xlsx")
        os.makedirs(ARCHIVES_PATH, exist_ok=True)
        df.to_excel(template_path, index=False, engine="openpyxl")

        # Відправляємо
        await message.answer_document(
            FSInputFile(template_path),
            caption=(
                "📋 Шаблон для імпорту\n\n"
                "Колонки:\n"
                "• в - відділ (номер)\n"
                "• г - група (текст)\n"
                "• а - артикул (8 цифр)\n"
                "• н - назва товару\n"
                "• м - місяців без руху\n"
                "• к - кількість (залишок)\n"
                "• с - сума (вартість залишку)\n\n"
                "Можна використовувати повні назви колонок українською."
            ),
        )

        # Видаляємо файл
        os.remove(template_path)

    except Exception as e:
        logger.error("Помилка створення шаблону: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка створення шаблону:\n{str(e)}")


# ==============================================================================
