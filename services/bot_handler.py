import logging
import os
from datetime import datetime
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

from config import ALLOWED_USERS_SET, REPORT_CHAT_ID, logger
from parsers import POSParser
from services import GoogleSheetsManager

logger = logging.getLogger(__name__)


class BotHandler:
    def __init__(self):
        self.sheets_manager = GoogleSheetsManager()
        self.user_data: Dict[int, Dict[str, str]] = {}

    def _is_allowed(self, user_id: int) -> bool:
        if ALLOWED_USERS_SET is None:
            return True
        return user_id in ALLOWED_USERS_SET

    def _format_report_response(self, name: str, date: str, shift: str, data) -> str:
        d = data.to_dict()
        # Helper to format values - show 0 instead of None for numeric fields
        def fmt(field, default='Н/Д'):
            val = d.get(field)
            if val is None:
                return '0'
            return val
        
        return (
            f"<b>{name}</b> | {date} | {shift}\n\n"
            f"💵 <b>Итого за смену</b> - {fmt('total')}\n"
            f"🕹 <b>Игровое время</b> - {fmt('game_time')}\n"
            f"🍗 <b>Бар</b> - {fmt('bar')}\n"
            f"🥬 <b>Нал</b> - {fmt('cash')}\n"
            f"🛜 <b>Безнал</b> - {fmt('cashless')}\n"
            f"🖥 <b>СБП</b> - {fmt('sbp')}\n"
            f"💳 <b>Эквайринг</b> - {fmt('acquiring')}\n"
            f"🍾 <b>Услуги</b> - {fmt('services')}\n"
            f"💵 <b>Возврат нал</b> - {fmt('return_cash')}\n"
            f"🛜 <b>Возврат безнал</b> - {fmt('return_cashless')}"
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            logger.warning("Received update without message in start_command")
            return

        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        is_group = update.effective_chat.type != "private"

        args = context.args
        if args:
            text = " ".join(args)
            parts = text.split()
            name = parts[0] if parts else user_name
            date = None

            if len(parts) > 1:
                import re
                for part in parts:
                    if re.match(r"\d{2}\.\d{2}\.\d{4}", part):
                        date = part
                        break

            if not date:
                date = datetime.now().strftime("%d.%m.%Y")

            self.user_data[user_id] = {"name": name, "date": date}

            msg_prefix = f"✅ Принято для <b>{user_name}</b>!\n" if is_group else "✅ Принято!\n"
            await update.message.reply_text(
                f"{msg_prefix}"
                f"👤 Имя: <b>{name}</b>\n"
                f"📅 Дата: <b>{date}</b>\n\n"
                f"Теперь отправьте скриншот из кассового ПО.",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            "👋 Привет! Отправьте мне скриншот из кассового ПО.\n\n"
            "Вы также можете указать имя и дату перед скриншотом:\n"
            "`/start Имя Дата`\n\n"
            "Пример: `/start Максим 25.03.2026`"
        )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            logger.warning("Received update without message in handle_photo")
            return

        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        is_group = update.effective_chat.type != "private"

        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        file_path = f"temp_{user_id}_{int(datetime.now().timestamp())}.jpg"
        await file.download_to_drive(file_path)

        try:
            processing_msg = await update.message.reply_text("⏳ Обрабатываю скриншот...")

            text = POSParser.extract_text_from_image(file_path)
            logger.info(f"Extracted text:\n{text}")

            data = POSParser.parse_report(text)
            logger.info(f"Parsed data: {data.to_dict()}")

            name = self.user_data.get(user_id, {}).get("name", user_name)
            date = self.user_data.get(user_id, {}).get("date", datetime.now().strftime("%d.%m.%Y"))

            current_hour = datetime.now().hour
            shift = POSParser.determine_shift(current_hour)

            response = self._format_report_response(name, date, shift, data)
            await processing_msg.edit_text(response, parse_mode="HTML")

            # Duplicate to report chat if configured
            if REPORT_CHAT_ID and not is_group:
                logger.info(f"Attempting to send report to chat {REPORT_CHAT_ID}")
                try:
                    await context.bot.send_message(
                        chat_id=int(REPORT_CHAT_ID),
                        text=f"📊 <b>Отчёт от {user_name}</b>\n\n{response}",
                        parse_mode="HTML",
                    )
                    await update.message.reply_text("✅ Отчёт также отправлен в рабочий чат!")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to send to report chat {REPORT_CHAT_ID}: {error_msg}")
                    if "chat not found" in error_msg.lower() or "400" in error_msg:
                        await update.message.reply_text(
                            f"⚠️ Не удалось отправить в чат. Проверьте ID чата в .env (REPORT_CHAT_ID={REPORT_CHAT_ID}).\n"
                            f"Убедитесь, что бот добавлен в этот чат как администратор."
                        )
                    else:
                        await update.message.reply_text(f"⚠️ Ошибка отправки в чат: {error_msg}")

            # Save to Google Sheets
            try:
                self.sheets_manager.append_report(name, date, shift, data)
                await update.message.reply_text("✅ Данные успешно сохранены в Google Таблицу!")
            except Exception as e:
                logger.error(f"Error saving to Google Sheets: {e}")
                await update.message.reply_text(
                    "⚠️ Данные распознаны, но произошла ошибка при сохранении в таблицу."
                )

            self.user_data.pop(user_id, None)

        except Exception as e:
            logger.error(f"Error processing photo: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке скриншота. Попробуйте еще раз."
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    async def handle_text(self, update: Update):
        if update.message is None:
            logger.warning("Received update without message in handle_text")
            return

        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        text = update.message.text.strip()
        is_group = update.effective_chat.type != "private"
        user_name = update.effective_user.first_name

        if text.startswith("/start"):
            return

        parts = text.split()
        name = parts[0] if parts else update.effective_user.first_name
        date = None

        if len(parts) > 1:
            import re
            date_pattern = r"\d{2}\.\d{2}\.\d{4}"
            for part in parts:
                if re.match(date_pattern, part):
                    date = part
                    break

        if not date:
            date = datetime.now().strftime("%d.%m.%Y")

        self.user_data[user_id] = {"name": name, "date": date}

        if is_group:
            await update.message.reply_text(
                f"✅ Принято для <b>{user_name}</b>!\n"
                f"👤 Имя: <b>{name}</b>\n"
                f"📅 Дата: <b>{date}</b>\n\n"
                f"Теперь отправьте скриншот из кассового ПО.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"✅ Принято!\n"
                f"👤 Имя: <b>{name}</b>\n"
                f"📅 Дата: <b>{date}</b>\n\n"
                f"Теперь отправьте скриншот из кассового ПО.",
                parse_mode="HTML",
            )
