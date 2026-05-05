import logging
from datetime import datetime, timedelta
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
    RECEIVER = "receiver"
    CONFIRM = "confirm"


class BotHandler:
    def __init__(self):
        self.sheets_manager = GoogleSheetsManager()
        self.user_data: Dict[int, Dict[str, str]] = {}
        self.pending_media: Dict[int, Dict] = {}

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
            f"Смену принял: {get('receiver', '')}\n"
        )


    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        self._clear_user_data(user_id)

        # === УМНОЕ ОПРЕДЕЛЕНИЕ ДАТЫ ДЛЯ СМЕН ===
        now = datetime.now()
        current_hour = now.hour

        # Определяем смену
        try:
            from config import NIGHT_SHIFT_START_HOUR, DAY_SHIFT_START_HOUR
            is_night = current_hour >= NIGHT_SHIFT_START_HOUR or current_hour < DAY_SHIFT_START_HOUR
            shift = "Ночь" if is_night else "День"
        except ImportError:
            shift = "День"
            is_night = False

        # Если сейчас ночь/раннее утро И смена "Ночь" → дата = вчера
        if is_night and shift == "Ночь" and current_hour < DAY_SHIFT_START_HOUR:
            # Ночная смена, которая заканчивается утром, относится к вчерашнему дню
            report_date = (now - timedelta(days=1)).strftime("%d.%m.%Y")
            logger.info(f"🌙 Ночная смена: {report_date} (фактически {now.strftime('%d.%m')})")
        else:
            report_date = now.strftime("%d.%m.%Y")

        self.user_data[user_id] = {
            "date": report_date,
            "shift": shift,
            "state": InputState.IDLE
        }
        # === КОНЕЦ БЛОКА ===

        await update.message.reply_text(
            f"👋 Привет! Начинаем отчет за смену.\n\n"
            f"📅 Дата: {report_date}\n"
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

    async def _ask_receiver(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.RECEIVER)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👤 Введите имя сотрудника, принявшего смену:"
        )


    async def _ask_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._set_user_state(update.effective_user.id, InputState.PHOTO)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📸 Прикрепите фото конверта с чеками:")

    async def _ask_confirm_direct(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, report_text: str):
        """Показывает подтверждение при вызове из таймера (без update.message)"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton("✏️ Редактировать", callback_data="edit_report"),
                InlineKeyboardButton("✅ Подтверждаю", callback_data="send_report")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if user_id in self.pending_media:
            self.pending_media[user_id]["report_text"] = report_text

        await context.bot.send_message(
            chat_id=user_id,
            text=f"📋 Проверьте данные перед отправкой:\n\n{report_text}",
            reply_markup=reply_markup
        )

    async def _ask_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE, report_text: str):
        """Показывает отчет и кнопки подтверждения (когда есть update.message)"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton("✏️ Редактировать", callback_data="edit_report"),
                InlineKeyboardButton("✅ Подтверждаю", callback_data="send_report")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        user_id = update.effective_user.id
        if user_id in self.pending_media:
            self.pending_media[user_id]["report_text"] = report_text

        await update.message.reply_text(
            f"📋 Проверьте данные перед отправкой:\n\n{report_text}",
            reply_markup=reply_markup
        )

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
            await self._ask_receiver(update, context)
            return

        if state == InputState.RECEIVER:
            if len(text.strip()) < 2:
                await update.message.reply_text("❌ Пожалуйста, введите имя (минимум 2 символа):")
                return

            self.user_data[user_id]["receiver"] = text.strip()
            await update.message.reply_text(f"✅ Принято: {text.strip()}\n\nНачинаем ввод данных:")

            await self._ask_total(update, context)
            return

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
                InputState.RECEIVER: self._ask_total,
                InputState.TOTAL: self._ask_game_time,
                InputState.GAME_TIME: self._ask_bar,
                InputState.BAR: self._ask_cash,
                InputState.CASH: self._ask_cashless,
                InputState.CASHLESS: self._ask_sbp,
                InputState.SBP: self._ask_acquiring,
                InputState.ACQUIRING: self._ask_services,
                InputState.SERVICES: self._ask_smoke,
                InputState.SMOKE: self._ask_return_cash,
                InputState.RETURN_CASH: self._ask_return_cashless,
                InputState.RETURN_CASHLESS: self._ask_cash_in,
                InputState.CASH_IN: self._ask_expense,
                InputState.EXPENSE: self._ask_envelope,
                InputState.ENVELOPE: self._ask_cash_remainder,
                InputState.CASH_REMAINDER: self._ask_photo,
            }
            if next_step.get(state):
                await next_step[state](update, context)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки подтверждения"""
        query = update.callback_query
        if query is None:
            return

        await query.answer()
        user_id = query.from_user.id
        data = query.data

        if data == "send_report":
            # ✅ Пользователь подтвердил — реально отправляем
            await query.edit_message_text("⏳ Отправляю отчёт...")
            await self._send_report_final(context, user_id)



        elif data == "edit_report":
            # ✏️ Пользователь хочет редактировать — сбрасываем всё
            user_id = query.from_user.id
            # Очищаем временные данные (фото, таймер, отчет)
            if user_id in self.pending_media:
                # Пробуем удалить таймер, если он ещё активен
                timer = self.pending_media[user_id].get("timer")
                if timer:
                    try:
                        timer.schedule_removal()
                    except Exception:
                        pass
                self.pending_media.pop(user_id, None)
            # Сбрасываем состояние пользователя к началу ввода данных
            self._set_user_state(user_id, InputState.TOTAL)
            await query.edit_message_text(
                "✏️ Режим редактирования. Введите новое значение для первого поля:"
            )
            await self._ask_total(update, context)


    # --- Обработчик фото ---
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото (поддержка одиночных и альбомов)"""
        if update.message is None:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        user_id = update.effective_user.id
        state = self._get_user_state(user_id)

        if state != InputState.PHOTO:
            return

        message = update.message
        media_group_id = message.media_group_id

        # === Инициализация сбора альбома ===
        if user_id not in self.pending_media:
            self.pending_media[user_id] = {
                "photos": [],
                "report_text": None,
                "media_group_id": media_group_id,
                "timer": None
            }

        pending = self.pending_media[user_id]

        # Скачиваем фото в память (не на диск, чтобы потом отправить)
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        pending["photos"].append({
            "bytes": bytes(photo_bytes),
            "filename": f"{message.photo[-1].file_unique_id}.jpg"
        })

        logger.info(f"📸 Получено фото {len(pending['photos'])} от пользователя {user_id}" +
                    (f" (альбом: {media_group_id})" if media_group_id else ""))

        # === Если это альбом — ждём остальные фото ===
        if media_group_id:
            # Отменяем предыдущий таймер, если был (безопасно)
            if pending["timer"]:
                try:
                    pending["timer"].schedule_removal()
                except Exception:
                    # Таймер уже выполнен или удалён — это нормально
                    pass

            # Планируем обработку через 2 секунды
            pending["timer"] = context.job_queue.run_once(
                lambda ctx: self._process_pending_photos(ctx, user_id),
                when=2,
                name=f"process_photos_{user_id}"
            )

            if len(pending["photos"]) == 1:
                await message.reply_text("⏳ Загрузка фото...")
            return  # Ждём остальные фото или таймаут

        # === Одиночное фото — обрабатываем сразу ===
        await self._process_pending_photos(context, user_id)

    async def _process_pending_photos(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, update: Update = None):
        """
        Генерирует отчет и показывает кнопки подтверждения.
        НЕ сохраняет и НЕ отправляет — это делает handle_callback после подтверждения.
        """
        if user_id not in self.pending_media:
            return

        pending = self.pending_media[user_id]
        photos = pending["photos"]

        if not photos:
            self.pending_media.pop(user_id, None)
            return

        try:
            if pending["report_text"] is None:
                pending["report_text"] = self._generate_report_text(self.user_data[user_id])
            report_text = pending["report_text"]

            if update and update.message:
                await self._ask_confirm(update, context, report_text)
            else:
                await self._ask_confirm_direct(context, user_id, report_text)

            return

        except Exception as e:
            logger.error(f"❌ Ошибка при показе подтверждения: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Произошла ошибка. Попробуйте ещё раз."
            )

    async def _send_report_final(self, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """
        Сохраняет в Google Sheets и отправляет фото в чат.
        Вызывается ТОЛЬКО после нажатия "✅ Подтверждаю".
        """
        if user_id not in self.pending_media:
            return

        pending = self.pending_media[user_id]
        photos = pending["photos"]
        report_text = pending.get("report_text", "")

        try:
            # 1. Сохраняем в Google Sheets
            try:
                d = self.user_data[user_id]
                report_obj = POSReport(
                    total=d.get("total"), game_time=d.get("game_time"), bar=d.get("bar"),
                    cash=d.get("cash"), cashless=d.get("cashless"), sbp=d.get("sbp"),
                    acquiring=d.get("acquiring"), services=d.get("services"), smoke=d.get("smoke"),
                    return_cash=d.get("return_cash"), return_cashless=d.get("return_cashless"),
                    cash_in=d.get("cash_in"), expense=d.get("expense"), envelope=d.get("envelope"),
                    cash_remainder=d.get("cash_remainder"),
                )
                self.sheets_manager.append_report(d["name"], d["date"], d.get("shift", ""), report_obj)
            except Exception as e:
                logger.error(f"Error saving to Google Sheets: {e}")
                await context.bot.send_message(chat_id=user_id, text="⚠️ Ошибка при сохранении в таблицу.")

            # 2. Отправляем фото альбомом в рабочий чат
            photo_sent = False
            if REPORT_CHAT_ID_INT and photos:
                try:
                    from telegram import InputMediaPhoto
                    media_list = []
                    for i, photo_data in enumerate(photos):
                        if i == 0:
                            media = InputMediaPhoto(
                                media=photo_data["bytes"],
                                caption=report_text,
                                parse_mode="HTML"
                            )
                        else:
                            media = InputMediaPhoto(media=photo_data["bytes"])
                        media_list.append(media)

                    send_kwargs = {"chat_id": REPORT_CHAT_ID_INT, "media": media_list}
                    if REPORT_THREAD_ID_INT:
                        send_kwargs["message_thread_id"] = REPORT_THREAD_ID_INT

                    await context.bot.send_media_group(**send_kwargs)
                    photo_sent = True
                except Exception as e:
                    logger.error(f"Failed to send album: {e}")

            # 3. Финальное сообщение пользователю
            if photo_sent:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Отчёт и {len(photos)} фото отправлены в чат клуба!\nВозвращайтесь для следующей смены."
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Отчёт принят!\nВозвращайтесь для следующей смены."
                )

        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчёта: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ошибка при отправке. Попробуйте ещё раз."
            )
        finally:
            # Очищаем данные в любом случае
            self.pending_media.pop(user_id, None)
            self._clear_user_data(user_id)