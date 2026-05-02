import logging
import os
from datetime import datetime
from typing import Dict
from enum import Enum
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import (
    ALLOWED_USERS_SET,
    REPORT_CHAT_ID_INT,
    REPORT_THREAD_ID_INT,
    logger
)
from services import GoogleSheetsManager
from models import POSReport

logger = logging.getLogger(__name__)

# Папка для сохранения фото
PHOTOS_DIR = Path("photos")
PHOTOS_DIR.mkdir(exist_ok=True)


class InputState(Enum):
    """Состояния диалога для пошагового ввода"""
    IDLE = "idle"
    NAME = "name"
    ACQUIRING = "acquiring"
    SBP = "sbp"
    CASH = "cash"
    BAR = "bar"
    SERVICES = "services"
    RETURNS = "returns"
    EXCHANGE = "exchange"
    ENVELOPE = "envelope"
    EXPENSE = "expense"
    PHOTO = "photo"


class BotHandler:
    def __init__(self):
        self.sheets_manager = GoogleSheetsManager()
        self.user_data: Dict[int, Dict[str, str]] = {}

    def _is_allowed(self, user_id: int) -> bool:
        if ALLOWED_USERS_SET is None:
            return True
        return user_id in ALLOWED_USERS_SET

    def _get_user_state(self, user_id: int) -> InputState:
        return self.user_data.get(user_id, {}).get("state", InputState.IDLE)

    def _set_user_state(self, user_id: int, state: InputState):
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
        self.user_data[user_id]["state"] = state

    def _clear_user_data(self, user_id: int):
        if user_id in self.user_data:
            self.user_data[user_id] = {}

    def _format_number(self, value: str) -> str:
        """Форматирует число с пробелами (1000 -> 1 000)"""
        try:
            num = int(value)
            return f"{num:,}".replace(",", " ")
        except (ValueError, TypeError):
            return value

    def _generate_report_text(self,  data: Dict[str, str]) -> str:
        """Генерирует текст итогового отчета"""
        acquiring = int(data.get("acquiring", 0) or 0)
        sbp = int(data.get("sbp", 0) or 0)
        cash = int(data.get("cash", 0) or 0)
        bar = int(data.get("bar", 0) or 0)
        services = int(data.get("services", 0) or 0)
        returns = int(data.get("returns", 0) or 0)
        exchange = int(data.get("exchange", 0) or 0)
        envelope = int(data.get("envelope", 0) or 0)
        expense = int(data.get("expense", 0) or 0)

        game_time = bar + services
        total = cash + sbp + acquiring
        cashless = sbp + acquiring
        cash_remainder = cash - expense - envelope + exchange

        name = data.get("name", "Неизвестно")
        date = data.get("date", datetime.now().strftime("%d.%m.%Y"))
        shift = data.get("shift", "День")

        report = (
            f"{name} {date} {shift}\n"
            f"{'=' * 27}\n"
            f"💵 Итого за смену - {self._format_number(str(total))}\n"
            f"🕹 Игровое время - {self._format_number(str(game_time))}\n"
            f"🍗 Бар - {self._format_number(str(bar))}\n"
            f"🥬 Нал - {self._format_number(str(cash))}\n"
            f"🛜 Безнал - {self._format_number(str(cashless))}\n"
            f"🖥 СБП - {self._format_number(str(sbp))}\n"
            f"💳 Эквайринг - {self._format_number(str(acquiring))}\n"
            f"🍾 Услуги - {self._format_number(str(services))}\n"
            f"💵 Возврат нал - {self._format_number(str(returns))}\n"
            f"🛜 Возврат безнал - 0\n"
            f"{'—' * 25}\n"
            f"Касса:\n"
            f"Приход - {self._format_number(str(cash))}\n"
            f"Расход - {self._format_number(str(expense))}\n"
            f"В конверт - {self._format_number(str(envelope))}\n"
            f"Остаток в кассе - {self._format_number(str(cash_remainder))}\n"
            f"{'=' * 26}\n"
            f"Смену сдал: {name}\n"
        )
        return report

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка /start - начало сессии"""
        if update.message is None:
            return

        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id

        self._clear_user_data(user_id)
        self.user_data[user_id] = {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "state": InputState.IDLE
        }

        current_hour = datetime.now().hour
        try:
            from config import NIGHT_SHIFT_START_HOUR, DAY_SHIFT_START_HOUR
            if current_hour >= NIGHT_SHIFT_START_HOUR or current_hour < DAY_SHIFT_START_HOUR:
                shift = "Ночь"
            else:
                shift = "День"
        except ImportError:
            shift = "День"
        self.user_data[user_id]["shift"] = shift

        await update.message.reply_text(
            f"👋 Привет! Начинаем отчет за смену.\n\n"
            f"📅 Дата: {self.user_data[user_id]['date']}\n"
            f"🌙 Смена: {shift}\n\n"
            f"Отвечайте на сообщения бота цифрами (без пробелов и символов)."
        )

        await self._ask_name(update, context)

    # --- Цепочка запросов ---

    async def _ask_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self._set_user_state(user_id, InputState.NAME)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👤 Введите ваше имя (или инициалы):"
        )

    async def _ask_acquiring(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.ACQUIRING)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💳 Введите сумму Эквайринга:")

    async def _ask_sbp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.SBP)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💳 Введите сумму СБП:")

    async def _ask_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.CASH)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💵 Введите сумму Наличными:")

    async def _ask_bar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.BAR)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🍸 Введите сумму Бара:")

    async def _ask_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.SERVICES)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🍾 Введите сумму Услуг:")

    async def _ask_returns(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.RETURNS)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🔁 Введите сумму Возвратов:")

    async def _ask_exchange(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.EXCHANGE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💱 Введите сумму Размена в кассе:")

    async def _ask_envelope(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.ENVELOPE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📬 Введите сумму В конверте:")

    async def _ask_expense(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.EXPENSE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📉 Введите сумму Расхода:")

    async def _ask_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.PHOTO)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=" Прикрепите фото конверта с чеками:"
        )

    # --- Обработчики ввода ---

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        text = update.message.text.strip()
        state = self._get_user_state(user_id)

        if state == InputState.IDLE:
            return
        if state == InputState.PHOTO:
            await update.message.reply_text("📸 Сейчас жду фото, а не текст.")
            return

        if state == InputState.NAME:
            if len(text.strip()) < 2:
                await update.message.reply_text("❌ Пожалуйста, введите имя (минимум 2 символа):")
                return
            self.user_data[user_id]["name"] = text.strip()
            await update.message.reply_text(f"✅ Принято: {text.strip()}\n\nНачинаем ввод данных:")
            await self._ask_acquiring(update, context)
            return

        try:
            value = int(text.replace(" ", "").replace(",", ""))
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите только цифры (без символов):")
            return

        if state == InputState.ACQUIRING:
            self.user_data[user_id]["acquiring"] = str(value)
            await self._ask_sbp(update, context)
        elif state == InputState.SBP:
            self.user_data[user_id]["sbp"] = str(value)
            await self._ask_cash(update, context)
        elif state == InputState.CASH:
            self.user_data[user_id]["cash"] = str(value)
            await self._ask_bar(update, context)
        elif state == InputState.BAR:
            self.user_data[user_id]["bar"] = str(value)
            await self._ask_services(update, context)
        elif state == InputState.SERVICES:
            self.user_data[user_id]["services"] = str(value)
            await self._ask_returns(update, context)
        elif state == InputState.RETURNS:
            self.user_data[user_id]["returns"] = str(value)
            await self._ask_exchange(update, context)
        elif state == InputState.EXCHANGE:
            self.user_data[user_id]["exchange"] = str(value)
            await self._ask_envelope(update, context)
        elif state == InputState.ENVELOPE:
            self.user_data[user_id]["envelope"] = str(value)
            await self._ask_expense(update, context)
        elif state == InputState.EXPENSE:
            self.user_data[user_id]["expense"] = str(value)
            await self._ask_photo(update, context)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        state = self._get_user_state(user_id)

        if state != InputState.PHOTO:
            return

        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        name = self.user_data[user_id].get("name", "unknown").replace(" ", "_")
        date = self.user_data[user_id].get("date", datetime.now().strftime("%d.%m.%Y"))
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{name}_{date}_{timestamp}.jpg"
        filepath = PHOTOS_DIR / filename

        await file.download_to_drive(str(filepath))
        file_size = photo.file_size / 1024

        await update.message.reply_text(f"✅ Фото сохранено: `{filename}` ({file_size:.1f} KB)", parse_mode="Markdown")

        report_text = self._generate_report_text(self.user_data[user_id])
        await update.message.reply_text(report_text)

        try:
            data = self.user_data[user_id]
            report_obj = POSReport(
                total=str(int(data.get("cash", 0)) + int(data.get("sbp", 0)) + int(data.get("acquiring", 0))),
                game_time=str(int(data.get("bar", 0)) + int(data.get("services", 0))),
                bar=data.get("bar", "0"),
                cash=data.get("cash", "0"),
                cashless=str(int(data.get("sbp", 0)) + int(data.get("acquiring", 0))),
                sbp=data.get("sbp", "0"),
                acquiring=data.get("acquiring", "0"),
                services=data.get("services", "0"),
                return_cash=data.get("returns", "0"),
                return_cashless="0",
            )

            self.sheets_manager.append_report(
                data["name"], data["date"], data["shift"], report_obj
            )
        except Exception as e:
            logger.error(f"Error saving to Google Sheets: {e}")
            await update.message.reply_text("️ Ошибка при сохранении в таблицу.")

        is_group = update.effective_chat.type != "private"

        if REPORT_CHAT_ID_INT and not is_group:
            try:
                send_kwargs = {
                    "chat_id": REPORT_CHAT_ID_INT,
                    "text": report_text,
                }
                if REPORT_THREAD_ID_INT:
                    send_kwargs["message_thread_id"] = REPORT_THREAD_ID_INT
                await context.bot.send_message(**send_kwargs)
                await update.message.reply_text("✅ Отчет отправлен в чат клуба!")
            except Exception as e:
                logger.error(f"Failed to send to report chat: {e}")
                await update.message.reply_text("✅ Принято, но не отправлено в чат.")
        else:
            await update.message.reply_text("✅ Отчет принят!")

        self._clear_user_data(user_id)