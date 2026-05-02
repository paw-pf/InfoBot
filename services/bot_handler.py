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

PHOTOS_DIR = Path("photos")
PHOTOS_DIR.mkdir(exist_ok=True)


class InputState(Enum):
    """Пошаговые состояния ввода строго по порядку отчёта"""
    IDLE = "idle"
    NAME = "name"
    TOTAL = "total"  # 💵 Итого за смену
    GAME_TIME = "game_time"  # 🕹 Игровое время
    BAR = "bar"  # 🍗 Бар
    CASH = "cash"  # 🥬 Нал
    CASHLESS = "cashless"  # 🛜 Безнал
    SBP = "sbp"  # 🖥 СБП
    ACQUIRING = "acquiring"  # Эквайринг
    SERVICES = "services"  # 🍾 Услуги
    SMOKE = "smoke" # 💭Кальяны
    RETURN_CASH = "return_cash"  # 💵 Возврат нал
    RETURN_CASHLESS = "return_cashless"  # 🛜 Возврат безнал
    CASH_IN = "cash_in"  # Приход
    EXPENSE = "expense"  # Расход
    ENVELOPE = "envelope"  # В конверт
    CASH_REMAINDER = "cash_remainder"  # Остаток в кассе
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

    def _generate_report_text(self, data: Dict[str, str]) -> str:
        get = data.get
        return (
            f"{'=' * 27}\n"
            f"💵 Итого за смену - {get('total', '0')}\n"
            f"🕹 Игровое время - {get('game_time', '0')}\n"
            f"🍗 Бар - {get('bar', '0')}\n"
            f"🥬 Нал - {get('cash', '0')}\n"
            f"🛜 Безнал - {get('cashless', '0')}\n"
            f"🖥 СБП - {get('sbp', '0')}\n"
            f"💳 Эквайринг - {get('acquiring', '0')}\n"
            f"🍾 Услуги - {get('services', '0')}\n"
            f"💭 Кальяны - {get('smoke', '0')}\n"
            f"💵 Возврат нал - {get('return_cash', '0')}\n"
            f"🛜 Возврат безнал - {get('return_cashless', '0')}\n"
            f"{'—' * 25}\n"
            f"Касса:\n"
            f"Приход - {get('cash_in', '0')}\n"
            f"Расход - {get('expense', '0')}\n"
            f"В конверт - {get('envelope', '0')}\n"
            f"Остаток в кассе - {get('cash_remainder', '0')}\n"
            f"{'=' * 26}\n"
            f"Смену сдал: {get('name', 'Неизвестно')}\n"
        )


    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Отвечайте на сообщения бота цифрами."
        )
        await self._ask_name(update, context)


    # --- Цепочка запросов строго по порядку ---
    async def _ask_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.NAME)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=" Введите ваше имя (или инициалы):")


    async def _ask_total(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.TOTAL)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💵 Введите сумму Итого за смену:")


    async def _ask_game_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.GAME_TIME)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🕹 Введите сумму Игровое время:")


    async def _ask_bar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.BAR)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🍗 Введите сумму Бар:")


    async def _ask_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.CASH)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🥬 Введите сумму Нал:")


    async def _ask_cashless(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.CASHLESS)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🛜 Введите сумму Безнал:")


    async def _ask_sbp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.SBP)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🛜 Введите сумму СБП:")


    async def _ask_acquiring(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.ACQUIRING)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💳 Введите сумму Эквайринг:")


    async def _ask_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.SERVICES)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🍾 Введите сумму Услуги:")

    async def _ask_smoke(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.SMOKE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💭Кальяны:")


    async def _ask_return_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.RETURN_CASH)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="💵 Введите сумму Возврат нал:")


    async def _ask_return_cashless(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.RETURN_CASHLESS)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🛜 Введите сумму Возврат безнал:")


    async def _ask_cash_in(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.CASH_IN)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=" Введите сумму Приход (Касса):")


    async def _ask_expense(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.EXPENSE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=" Введите сумму Расход:")


    async def _ask_envelope(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.ENVELOPE)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📬 Введите сумму В конверт:")


    async def _ask_cash_remainder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.CASH_REMAINDER)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🏦 Введите сумму Остаток в кассе:")


    async def _ask_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.PHOTO)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📸 Прикрепите фото конверта с чеками:")


    # --- Обработчик текста ---
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

        # Имя обрабатываем отдельно
        if state == InputState.NAME:
            if len(text) < 2:
                await update.message.reply_text("❌ Пожалуйста, введите имя (минимум 2 символа):")
                return
            self.user_data[user_id]["name"] = text
            await update.message.reply_text(f"✅ Принято: {text}\n\nНачинаем ввод данных:")
            await self._ask_total(update, context)
            return

        # Все остальные поля принимаем как есть (валидация только на пустоту)
        if not text:
            await update.message.reply_text("❌ Поле не может быть пустым. Введите 0, если суммы нет:")
            return

        # Маппинг состояний -> ключей в словаре
        state_to_key = {
            InputState.TOTAL: "total",
            InputState.GAME_TIME: "game_time",
            InputState.BAR: "bar",
            InputState.CASH: "cash",
            InputState.CASHLESS: "cashless",
            InputState.SBP: "sbp",
            InputState.ACQUIRING: "acquiring",
            InputState.SERVICES: "services",
            InputState.SMOKE: "smoke",
            InputState.RETURN_CASH: "return_cash",
            InputState.RETURN_CASHLESS: "return_cashless",
            InputState.CASH_IN: "cash_in",
            InputState.EXPENSE: "expense",
            InputState.ENVELOPE: "envelope",
            InputState.CASH_REMAINDER: "cash_remainder",
        }

        key = state_to_key.get(state)
        if key:
            self.user_data[user_id][key] = text

            # Переход к следующему шагу
            next_step = {
                InputState.TOTAL: self._ask_game_time,  # После Итого -> Игровое время
                InputState.GAME_TIME: self._ask_bar,  # После Игрового -> Бар
                InputState.BAR: self._ask_cash,  # После Бара -> Нал
                InputState.CASH: self._ask_cashless,  # После Нала -> Безнал
                InputState.CASHLESS: self._ask_sbp,  # После Безнала -> СБП
                InputState.SBP: self._ask_acquiring,  # После СБП -> Эквайринг
                InputState.ACQUIRING: self._ask_services,  # После Эквайринга -> Услуги
                InputState.SERVICES: self._ask_smoke,  # После Услуг -> Кальяны
                InputState.SMOKE: self._ask_return_cash,  # После Кальянов -> Возврат нал
                InputState.RETURN_CASH: self._ask_return_cashless,  # После Возврата нал -> Возврат безнал
                InputState.RETURN_CASHLESS: self._ask_cash_in,  # После Возврата безнал -> Приход
                InputState.CASH_IN: self._ask_expense,  # После Прихода -> Расход
                InputState.EXPENSE: self._ask_envelope,  # После Расхода -> В конверт
                InputState.ENVELOPE: self._ask_cash_remainder,  # После В конверт -> Остаток
                InputState.CASH_REMAINDER: self._ask_photo,  # После Остатка -> Фото
            }
            if next_step.get(state):
                await next_step[state](update, context)


    # --- Обработчик фото ---
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
        await update.message.reply_text("⏳ Загрузка и формирование отчёта...")

        # 1. Показываем отчёт пользователю
        report_text = self._generate_report_text(self.user_data[user_id])
        await update.message.reply_text(report_text)

        # 2. Сохраняем в Google Sheets (передаём сырые строки)
        try:
            d = self.user_data[user_id]
            report_obj = POSReport(
                total=d.get("total"),
                game_time=d.get("game_time"),
                bar=d.get("bar"),
                cash=d.get("cash"),
                cashless=d.get("cashless"),
                sbp=d.get("sbp"),
                acquiring=d.get("acquiring"),
                services=d.get("services"),
                smoke=d.get("smoke"),
                return_cash=d.get("return_cash"),
                return_cashless=d.get("return_cashless"),
                cash_in=d.get("cash_in"),
                expense=d.get("expense"),
                envelope=d.get("envelope"),
                cash_remainder=d.get("cash_remainder"),
            )
            self.sheets_manager.append_report(
                d["name"], d["date"], d.get("shift", ""), report_obj
            )
        except Exception as e:
            logger.error(f"Error saving to Google Sheets: {e}")
            await update.message.reply_text("⚠️ Ошибка при сохранении в таблицу.")

        # 3. Отправляем фото + отчёт в рабочий чат
        is_group = update.effective_chat.type != "private"
        photo_sent = False

        if REPORT_CHAT_ID_INT and not is_group:
            try:
                send_kwargs = {
                    "chat_id": REPORT_CHAT_ID_INT,
                    "caption": report_text,
                }
                if REPORT_THREAD_ID_INT:
                    send_kwargs["message_thread_id"] = REPORT_THREAD_ID_INT

                with open(filepath, 'rb') as f:
                    await context.bot.send_photo(photo=f, **send_kwargs)
                photo_sent = True
            except Exception as e:
                logger.error(f"Failed to send photo to chat: {e}")

        # 4. ️ МГНОВЕННОЕ УДАЛЕНИЕ ФОТО
        try:
            if filepath.exists():
                os.remove(filepath)
        except Exception as e:
            logger.warning(f"Не удалось удалить фото: {e}")

        # 5. Финальное сообщение
        if photo_sent:
            await update.message.reply_text("✅ Отчёт и фото отправлены в чат клуба!\nВозвращайтесь для следующей смены.")
        else:
            await update.message.reply_text("✅ Отчёт принят!\nВозвращайтесь для следующей смены.")

        self._clear_user_data(user_id)