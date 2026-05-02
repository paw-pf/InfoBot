import logging
from typing import Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, logger
from models import POSReport

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    def __init__(self):
        self.client = None
        self.sheet = None
        self._authenticate()

    def _authenticate(self):
        try:
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"],
            )
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)
            self.sheet = self.spreadsheet.sheet1
            logger.info("✅ Google Sheets подключены")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            raise

    @staticmethod
    def _clean_value(value: Optional[str]) -> str:
        """Очищает значение: убирает пробелы, заменяет пустое на '0'"""
        if not value:
            return "0"
        # Убираем пробелы как разделители тысяч (1 000 -> 1000) для корректной работы формул
        return str(value).replace(" ", "").strip()

    def append_report(self, name: str, date: str, shift: str, data: POSReport):
        try:
            expected_headers = [
                "Дата", "Смена", "Администратор",
                "💵 Итого", "🕹 Игровое", "🍗 Бар", "🥬 Нал", "🛜 Безнал",
                "🖥 СБП", "💳 Эквайринг", "🍾 Услуги", "💭 Кальяны",
                "💵 Возврат нал", "🛜 Возврат безнал",
                "📥 Приход", "📤 Расход", "📬 В конверт", "🏦 Остаток",
                "Примечание"
            ]

            # Проверка/создание заголовков
            current_headers = self.sheet.row_values(1)
            if current_headers != expected_headers:
                logger.info("🔄 Обновляю заголовки таблицы...")
                self.sheet.clear()
                self.sheet.append_row(expected_headers)
                self.sheet.format("A1:S1", {"textFormat": {"bold": True},
                                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}})

            row = [
                date,  # Дата
                shift,  # Смена
                name,  # Администратор
                self._clean_value(data.total),  # 💵 Итого
                self._clean_value(data.game_time),  # 🕹 Игровое
                self._clean_value(data.bar),  # 🍗 Бар
                self._clean_value(data.cash),  # 🥬 Нал
                self._clean_value(data.cashless),  # 🛜 Безнал
                self._clean_value(data.sbp),  # 🖥 СБП
                self._clean_value(data.acquiring),  # 💳 Эквайринг
                self._clean_value(data.services),  # 🍾 Услуги
                self._clean_value(data.smoke),  # 💭 Кальяны (новое)
                self._clean_value(data.return_cash),  # 💵 Возврат нал
                self._clean_value(data.return_cashless),  # 🛜 Возврат безнал
                self._clean_value(data.cash_in),  # 📥 Приход (новое)
                self._clean_value(data.expense),  # 📤 Расход (новое)
                self._clean_value(data.envelope),  # 📬 В конверт (новое)
                self._clean_value(data.cash_remainder),  # 🏦 Остаток (новое)
                "",  # Примечание (пусто)
            ]

            self.sheet.append_row(row)
            logger.info(f"📊 Отчёт сохранён: {name} | {date} | {shift}")

        except Exception as e:
            logger.error(f"❌ Ошибка записи в таблицу: {e}")
            raise