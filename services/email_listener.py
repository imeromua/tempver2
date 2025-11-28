# epicservice/services/email_listener.py

import imaplib
import email
import logging
import os
import asyncio
import pandas as pd
from email.header import decode_header
from datetime import datetime

from aiogram import Bot
from sqlalchemy import select, update, func

# Імпорти проєкту
from config import ARCHIVES_PATH, ADMIN_IDS, DB_TYPE, BACKUP_DIR, DB_NAME
from database.engine import async_session
from database.models import Product, StockHistory
from utils.import_processor import process_import_dataframe, read_excel_smart
from utils.markdown_corrector import format_filename_safe
from utils.force_save_helper import force_save_all_active_lists
from handlers.admin.import_handlers import create_backup_before_import

logger = logging.getLogger(__name__)

# --- НАЛАШТУВАННЯ EMAIL (можна винести в .env) ---
# Для Gmail потрібно створити "App Password" (Пароль додатка), звичайний пароль не підійде.
EMAIL_HOST = os.getenv("EMAIL_HOST", "imap.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 993))
EMAIL_USER = os.getenv("EMAIL_USER", "your_bot_email@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS", "your_app_password")

# Безпека
ALLOWED_SENDERS = os.getenv("ALLOWED_SENDERS", "admin@gmail.com").split(",")
SECRET_SUBJECT = os.getenv("EMAIL_SECRET_SUBJECT", "IMPORT_STOCK_CMD")

class EmailService:
    def __init__(self, bot: Bot):
        self.bot = bot

    def _connect_imap(self):
        mail = imaplib.IMAP4_SSL(EMAIL_HOST, EMAIL_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail

    async def check_email_and_process(self):
        """Головна функція, яку викликає планувальник."""
        # Запускаємо синхронну роботу з IMAP в окремому потоці, щоб не блокувати бота
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_check_email)

    def _sync_check_email(self):
        """Синхронна частина роботи з поштою."""
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            
            # Шукаємо тільки непрочитані листи
            status, messages = mail.search(None, '(UNSEEN)')
            
            if status != "OK" or not messages[0]:
                mail.logout()
                return

            for num in messages[0].split():
                try:
                    # Отримуємо лист
                    res, msg_data = mail.fetch(num, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Декодуємо тему
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else "utf-8")
                            
                            # Отримуємо відправника
                            from_ = msg.get("From")
                            sender_email = ""
                            if "<" in from_:
                                sender_email = from_.split("<")[1].strip(">")
                            else:
                                sender_email = from_

                            # --- ПЕРЕВІРКА БЕЗПЕКИ ---
                            if sender_email not in ALLOWED_SENDERS:
                                logger.warning(f"Email rejected from {sender_email}")
                                continue
                            
                            if subject.strip() != SECRET_SUBJECT:
                                logger.info(f"Email ignored (wrong subject): {subject}")
                                continue

                            logger.info(f"✅ Отримано команду на імпорт від {sender_email}")

                            # Обробка вкладень
                            self._process_attachments(msg)

                except Exception as e:
                    logger.error(f"Error processing email msg {num}: {e}")

            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"IMAP Connection Error: {e}")

    def _process_attachments(self, msg):
        """Шукає Excel файли і запускає імпорт."""
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if not filename: continue
            
            # Декодування імені файлу (якщо кирилиця)
            decoded_filename = decode_header(filename)[0][0]
            if isinstance(decoded_filename, bytes):
                encoding = decode_header(filename)[0][1] or 'utf-8'
                filename = decoded_filename.decode(encoding)

            if filename.lower().endswith(('.xlsx', '.xls', '.ods')):
                filepath = os.path.join(ARCHIVES_PATH, f"email_{datetime.now().strftime('%Y%m%d%H%M')}_{filename}")
                os.makedirs(ARCHIVES_PATH, exist_ok=True)
                
                with open(filepath, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                
                logger.info(f"Downloaded file: {filepath}")
                
                # 🔥 ЗАПУСКАЄМО АСИНХРОННУ ЛОГІКУ ІМПОРТУ
                # Ми все ще в синхронному потоці, тому треба створити задачу в головному циклі
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._run_full_import_process(filepath, filename))
                loop.close()
                return # Беремо тільки перший файл

    async def _run_full_import_process(self, file_path: str, original_filename: str):
        """
        Повна логіка: Force Save -> Backup -> Import -> Report
        """
        # 1. Сповіщаємо адміна
        if ADMIN_IDS:
            await self.bot.send_message(
                ADMIN_IDS[0], 
                f"📧 **Отримано файл поштою:** `{original_filename}`\n⏳ Починаю автоматичний імпорт..."
            )

        # 2. FORCE SAVE (Правило користувача)
        saved_count = await force_save_all_active_lists(self.bot)
        if saved_count > 0:
            if ADMIN_IDS:
                await self.bot.send_message(ADMIN_IDS[0], f"⚠️ Примусово збережено списки **{saved_count}** користувачів.")

        # 3. BACKUP
        await create_backup_before_import()

        # 4. IMPORT (Копія логіки з import_handlers, але без FSM)
        try:
            loop = asyncio.get_running_loop()
            df, _ = await loop.run_in_executor(None, read_excel_smart, file_path)
            processed_df, validation = await loop.run_in_executor(None, process_import_dataframe, df)

            if not validation.is_valid:
                error_msg = f"❌ **Помилка валідації (Email Import):**\n" + "\n".join(validation.errors[:5])
                if ADMIN_IDS: await self.bot.send_message(ADMIN_IDS[0], error_msg)
                return

            # Логіка запису в БД
            stats = {"added": 0, "updated": 0, "reactivated": 0, "deactivated": 0, "zero": 0}
            file_articles = set()

            async with async_session() as session:
                res_all = await session.execute(select(Product.артикул).where(Product.активний == True))
                db_active = set(res_all.scalars().all())

                for _, row in processed_df.iterrows():
                    try:
                        art = str(row["артикул"])
                        file_articles.add(art)
                        qty_str = str(row["кількість"]).replace('.', ',')
                        price_float = float(row["ціна"]) if row["ціна"] else 0.0
                        
                        try:
                            if float(str(row["кількість"]).replace(",", ".")) == 0: stats["zero"] += 1
                        except: pass

                        res = await session.execute(select(Product).where(Product.артикул == art))
                        existing = res.scalar_one_or_none()

                        if existing:
                            if not existing.активний:
                                existing.активний = True
                                stats["reactivated"] += 1
                            
                            if existing.кількість != qty_str:
                                hist = StockHistory(
                                    product_id=existing.id, articul=art,
                                    old_quantity=existing.кількість, new_quantity=qty_str,
                                    change_source="email_import"
                                )
                                session.add(hist)
                            
                            existing.кількість = qty_str
                            if row["ціна"]: existing.ціна = price_float
                            if row["сума_залишку"]: existing.сума_залишку = float(row["сума_залишку"])
                            if row["місяці_без_руху"]: existing.місяці_без_руху = int(row["місяці_без_руху"])
                            if row["назва"]: existing.назва = row["назва"]
                            if row["група"]: existing.група = row["група"]
                            if row["відділ"]: existing.відділ = row["відділ"]
                            
                            stats["updated"] += 1
                        else:
                            new_p = Product(
                                articul=art, назва=row["назва"] or "N/A", 
                                відділ=row["відділ"] or 0, група=row["група"] or "",
                                кількість=qty_str, ціна=price_float,
                                сума_залишку=row["сума_залишку"] or 0.0,
                                місяці_без_руху=row["місяці_без_руху"] or 0,
                                відкладено=0, активний=True
                            )
                            session.add(new_p)
                            stats["added"] += 1
                    except: pass

                # Деактивація
                to_deact = db_active - file_articles
                if to_deact:
                    await session.execute(
                        update(Product).where(Product.артикул.in_(to_deact)).values(активний=False)
                    )
                    stats["deactivated"] = len(to_deact)

                await session.commit()

            # Звіт
            report = (
                f"📧 **EMAIL ІМПОРТ ЗАВЕРШЕНО!**\n"
                f"📄 Файл: `{format_filename_safe(original_filename)}`\n\n"
                f"➕ Нових: {stats['added']}\n"
                f"🔄 Оновлено: {stats['updated']}\n"
                f"🔴 Деактивовано: {stats['deactivated']}\n"
                f"♻️ Відновлено: {stats['reactivated']}"
            )
            
            if ADMIN_IDS: await self.bot.send_message(ADMIN_IDS[0], report)
            
        except Exception as e:
            logger.error(f"Email import logic error: {e}", exc_info=True)
            if ADMIN_IDS: await self.bot.send_message(ADMIN_IDS[0], f"❌ Помилка email імпорту: {e}")
        finally:
            if os.path.exists(file_path): os.remove(file_path)