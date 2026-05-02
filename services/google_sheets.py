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
    def _fmt_money(value: Optional[str], prefix: str = "", with_rub: bool = False) -> str:
        """Формат: 1000 -> 1 000,00 | с опцией 'р.' или '₽'"""
        if not value:
            return "0,00"
        try:
            clean = str(value).replace(" ", "").replace(",", ".")
            num = float(clean)
            formatted = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
            if with_rub:
                return f"{prefix}{formatted} ₽"
            return f"{prefix}{formatted}"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _fmt_game_time(value: Optional[str]) -> str:
        """Формат: р.12 345 (без копеек)"""
        if not value:
            return "р.0"
        try:
            clean = str(value).replace(" ", "").replace(",", ".")
            num = float(clean)
            formatted = f"{num:,.0f}".replace(",", " ")
            return f"р.{formatted}"
        except (ValueError, TypeError):
            return "р.0"

    def append_report(self, name: str, date: str, shift: str, data: POSReport):
        try:
            def to_float(val: Optional[str]) -> float:
                if not val:
                    return 0.0
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except (ValueError, TypeError):
                    return 0.0

            # === Значения ===
            total = to_float(data.total)
            game_time = to_float(data.game_time)
            bar = to_float(data.bar)
            cash = to_float(data.cash)
            cashless = to_float(data.cashless)
            sbp = to_float(data.sbp)
            acquiring = to_float(data.acquiring)
            smoke = to_float(data.smoke)
            return_cash = to_float(data.return_cash)
            return_cashless = to_float(data.return_cashless)
            expense = to_float(data.expense)
            cash_remainder = to_float(data.cash_remainder)

            # === Расчёты ===
            sbp_plus_beznal = sbp + cashless
            acquiring_commission = acquiring * 0.025
            acquiring_to_bank = acquiring - acquiring_commission
            pct_acquiring = (acquiring_commission / acquiring * 100) if acquiring > 0 else 0
            pct_sbp = (sbp / total * 100) if total > 0 else 0

            # === Заголовки СТРОГО как в вашей таблице (20 колонок) ===
            # Первая колонка — "Дата", а не пустая строка!
            expected_headers = [
                "Дата", "Смена", "Администратор", "Z-отчет",
                "Игровое время + PS", "Кальян", "бар", "нал",
                "СБП+БЕЗНАЛ", "СБП", "Эквайринг", "Равно?",
                "ЭКВАЙРИНГ! в банк", "% эвк", "% сбп", "Расход",
                "Возврат безнал", "Возврат нал", "Инкассация", ""
            ]

            # Проверяем и создаём заголовки только если таблица пустая
            current_headers = self.sheet.row_values(1)
            if not current_headers or all(h.strip() == "" for h in current_headers):
                logger.info("🔄 Создаю заголовки таблицы...")
                self.sheet.append_row(expected_headers)
                self.sheet.format("A1:T1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}})

            # === Формируем строку данных (20 колонок, порядок как в headers) ===
            row = [
                date,                           # A: Дата (пт 1.05.2026)
                shift,                          # B: Смена
                name,                           # C: Администратор
                self._fmt_money(data.total),    # D: Z-отчет
                self._fmt_game_time(data.game_time),  # E: Игровое время + PS
                self._fmt_money(data.smoke),    # F: Кальян (берём из smoke)
                self._fmt_money(data.bar),      # G: бар
                self._fmt_money(data.cash),     # H: нал
                f"р.{self._fmt_money(sbp_plus_beznal)}",  # I: СБП+БЕЗНАЛ
                self._fmt_money(data.sbp),      # J: СБП
                self._fmt_money(data.acquiring),# K: Эквайринг
                "",                           # L: Равно?
                self._fmt_money(acquiring_to_bank),  # M: ЭКВАЙРИНГ! в банк
                f"{pct_acquiring:.2f}".replace(".", ","),  # N: % эвк
                f"{pct_sbp:.2f}".replace(".", ","),        # O: % сбп
                self._fmt_money(data.expense),  # P: Расход
                self._fmt_money(data.return_cashless),  # Q: Возврат безнал
                self._fmt_money(data.return_cash),      # R: Возврат нал
                "",                             # S: Инкассация
                f"{self._fmt_money(cash_remainder)} ₽"  # T: Остаток с ₽
            ]

            self.sheet.append_row(row)
            logger.info(f"📊 Отчёт сохранён: {name} | {date} | {shift}")

        except Exception as e:
            logger.error(f"❌ Ошибка записи в таблицу: {e}")
            raise