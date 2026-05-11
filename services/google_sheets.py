import datetime
import logging
import re
from typing import Optional

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
        self._set_active_sheet()

    def _authenticate(self):
        try:
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"],
            )
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)
            logger.info("✅ Google Sheets подключены")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            raise

    def _set_active_sheet(self):
        """Находит или создает лист с названием 'Отчеты MM.YYYY' за текущий месяц"""
        now = datetime.datetime.now()
        target_name = f"Отчеты {now.month:02d}.{now.year}"

        try:
            self.sheet = self.spreadsheet.worksheet(target_name)
            logger.info(f"📅 Подключен к листу: '{self.sheet.title}'")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"🆕 Лист '{target_name}' не найден. Создаю новый...")
            self.sheet = self.spreadsheet.add_worksheet(title=target_name, rows=1000, cols=20)
            logger.info(f"✅ Создан новый лист: '{self.sheet.title}'")

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

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """
        Нормализует дату к формату 'день.месяц' где:
        - день БЕЗ ведущего нуля: 4
        - месяц С ведущим нулем: 05
        Примеры:
        - '4.05.2026' → '4.05'
        - '04.05.2026' → '4.05'
        - 'пт 4.5' → '4.05'
        - '04.5.2026' → '4.05'
        """
        match = re.search(r'(\d{1,2})\.(\d{1,2})', date_str)
        if match:
            # День: убираем ведущие нули (04 → 4, 4 → 4)
            day = match.group(1).lstrip('0') or '0'
            # Месяц: добавляем ведущий ноль если нужно (5 → 05, 05 → 05)
            month = match.group(2).zfill(2)
            return f"{day}.{month}"
        return date_str.strip()

    def _find_row(self, date: str, shift: str) -> Optional[int]:
        """
        Ищет строку по дате и смене.
        Дата нормализуется без ведущих нулей, смена — по вхождению.
        """
        try:
            all_values = self.sheet.get_all_values()

            # Нормализуем дату: "04.05.2026" → "4.5"
            target_date_core = self._normalize_date(date)
            # Смена: "День" → "день"
            target_shift_lower = shift.strip().lower()

            last_date_core = None

            logger.info(f"🔍 Поиск: дата='{target_date_core}', смена='{target_shift_lower}'")

            for row_idx, row in enumerate(all_values, start=1):
                if row_idx == 1:
                    continue

                raw_date = str(row[0]).strip() if len(row) > 0 else ""
                raw_shift = str(row[1]).strip() if len(row) > 1 else ""

                # Пропускаем служебные строки
                skip = ['итого', 'выручка', 'прогноз', 'план', '#ref', 'администратор', 'z-отчет']
                if any(kw in raw_date.lower() or kw in raw_shift.lower() for kw in skip):
                    continue

                # Наследование даты
                if raw_date and not raw_date.startswith('#'):
                    last_date_core = self._normalize_date(raw_date)

                if not last_date_core:
                    continue

                # Сравнение
                date_match = target_date_core == last_date_core
                shift_match = target_shift_lower in raw_shift.lower()

                if date_match and shift_match:
                    logger.info(f"✅ СОВПАДЕНИЕ! Строка {row_idx}: '{raw_date}' | '{raw_shift}'")
                    return row_idx

            logger.warning(f"❌ Не найдено: '{target_date_core}' | '{target_shift_lower}'")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}", exc_info=True)
            return None

    @staticmethod
    def _fmt_raw(value: Optional[str]) -> float:
        """Возвращает число для записи в ячейки с формулами (без форматирования)"""
        if not value:
            return 0.0
        try:
            # Убираем пробелы, заменяем запятую на точку, преобразуем в float
            clean = str(value).replace(" ", "").replace(",", ".")
            return float(clean)
        except (ValueError, TypeError):
            return 0.0

    def _update_row(self, row_idx: int, name: str, date: str, shift: str, data: POSReport) -> bool:
        """
        Записывает данные:
        - В формульные колонки (F,G,H,J,K,P,Q,R) — сырые числа (для расчётов)
        - В текстовые колонки (A,B,C) — строки
        Колонки D,E,I,L,M,N,O,T не трогаем — там формулы.
        """
        try:
            cells_to_write = [
                (1, date),  # A: Дата (текст)
                (2, shift),  # B: Смена (текст)
                (3, name),  # C: Администратор (текст)
                # === ЯЧЕЙКИ С ФОРМУЛАМИ: пишем СЫРЫЕ ЧИСЛА ===
                (6, self._fmt_raw(data.smoke)),  # F: Кальян
                (7, self._fmt_raw(data.bar)),  # G: бар
                (8, self._fmt_raw(data.cash)),  # H: нал
                (10, self._fmt_raw(data.sbp)),  # J: СБП
                (11, self._fmt_raw(data.acquiring)),  # K: Эквайринг
                # (12) — L: Равно? → ФОРМУЛА, НЕ ПИШЕМ (оставляем пустым для формулы)
                (16, self._fmt_raw(data.expense)),  # P: Расход
                (17, self._fmt_raw(data.return_cashless)),  # Q: Возврат безнал
                (18, self._fmt_raw(data.return_cash)),  # R: Возврат нал
                (19, ""),  # S: Инкассация (пусто)
            ]

            logger.info(f"📤 Запись в строку {row_idx}: {[f'C{col}={val}' for col, val in cells_to_write]}")

            for col, value in cells_to_write:
                self.sheet.update_cell(row_idx, col, value)

            logger.info(f"✅ Строка {row_idx} обновлена. Формулы (D,E,I,L,M,N,O,T) пересчитаются автоматически.")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка записи: {e}", exc_info=True)
            return False

    def append_report(self, name: str, date: str, shift: str, data: POSReport):
        """
        Главная точка входа:
        1. Ищет готовую строку по дате и смене
        2. Заполняет ТОЛЬКО ячейки ввода, не затрагивая формулы
        """
        row_idx = self._find_row(date, shift)

        if row_idx:
            # ✅ Исправленный вызов: передаём все аргументы в правильном порядке
            success = self._update_row(row_idx, name, date, shift, data)
        else:
            logger.warning(f"⚠️ Строка для {date} | {shift} не найдена. Создаю новую.")
            # Если строки нет — создаём новую точечной записью
            new_idx = len(self.sheet.get_all_values()) + 1
            success = self._update_row(new_idx, name, date, shift, data)

        if not success:
            raise Exception("Не удалось сохранить отчёт в таблицу")