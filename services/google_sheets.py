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

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """
        Приводит дату к формату ДД.ММ для точного сравнения.
        Примеры:
        - "пт 1.05.2026" → "01.05"
        - "02.05.2026" → "02.05"
        - "2.05" → "02.05"
        """
        match = re.search(r'(\d{1,2})\.(\d{1,2})', date_str)
        if match:
            day = match.group(1).zfill(2)
            month = match.group(2).zfill(2)
            return f"{day}.{month}"
        return date_str.strip()

    def _find_row(self, date: str, shift: str) -> Optional[int]:
        """
        Ищет строку по дате и смене.
        Поддерживает пустые ячейки даты (наследуются от строки выше).
        """
        try:
            all_values = self.sheet.get_all_values()

            target_date = self._normalize_date(date)
            # Очищаем искомую смену от всего лишнего
            target_shift = shift.strip().lower().replace('\u200b', '').replace('\xa0', ' ').strip()

            last_date = None
            found_any = False  # Флаг: нашли ли хоть какие-то строки

            logger.info(f"🔍 Поиск: дата='{target_date}', смена='{target_shift}'")

            for row_idx, row in enumerate(all_values[1:], start=2):
                # Безопасное получение значений
                raw_date = row[0].strip() if len(row) > 0 and row[0] else ""
                raw_shift = row[1].strip() if len(row) > 1 and row[1] else ""

                # Пропускаем служебные строки
                if "итого" in raw_date.lower() or raw_date.startswith("#") or raw_date.startswith("Выручка"):
                    continue

                # Наследование даты: если ячейка пустая, берём последнюю известную
                if raw_date:
                    last_date = self._normalize_date(raw_date)

                # Если дата так и не определилась — пропускаем
                if not last_date:
                    continue

                current_date = last_date

                # Очищаем смену из таблицы
                clean_shift = raw_shift.lower().replace('\u200b', '').replace('\xa0', ' ').strip()

                # Сравнение
                if current_date == target_date and clean_shift == target_shift:
                    logger.info(f"✅ СОВПАДЕНИЕ! Строка {row_idx}")
                    return row_idx

            if not found_any:
                logger.warning("⚠️ В таблице нет данных для проверки (пустая таблица?)")
            else:
                logger.warning(f"❌ Не найдено. Искомое: '{target_date}' | '{target_shift}'")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}", exc_info=True)
            return None

    def _update_row(self, row_idx: int, data: POSReport, shift: str) -> bool:
        """Обновляет существующую строку данными"""
        try:
            def to_float(val: Optional[str]) -> float:
                if not val:
                    return 0.0
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except (ValueError, TypeError):
                    return 0.0

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

            # Расчёты
            sbp_plus_beznal = sbp + cashless
            acquiring_commission = acquiring * 0.025
            acquiring_to_bank = acquiring - acquiring_commission
            pct_acquiring = (acquiring_commission / acquiring * 100) if acquiring > 0 else 0
            pct_sbp = (sbp / total * 100) if total > 0 else 0

            # Формируем значения для колонок D-T (колонка A-C уже заполнены)
            updates = {
                4: self._fmt_money(data.total),  # D: Z-отчет
                5: self._fmt_game_time(data.game_time),  # E: Игровое время + PS
                6: self._fmt_money(data.smoke),  # F: Кальян
                7: self._fmt_money(data.bar),  # G: бар
                8: self._fmt_money(data.cash),  # H: нал
                9: f"р.{self._fmt_money(sbp_plus_beznal)}",  # I: СБП+БЕЗНАЛ
                10: self._fmt_money(data.sbp),  # J: СБП
                11: self._fmt_money(data.acquiring),  # K: Эквайринг
                12: "",  # L: Равно?
                13: self._fmt_money(acquiring_to_bank),  # M: ЭКВАЙРИНГ! в банк
                14: f"{pct_acquiring:.2f}".replace(".", ","),  # N: % эвк
                15: f"{pct_sbp:.2f}".replace(".", ","),  # O: % сбп
                16: self._fmt_money(data.expense),  # P: Расход
                17: self._fmt_money(data.return_cashless),  # Q: Возврат безнал
                18: self._fmt_money(data.return_cash),  # R: Возврат нал
                19: "",  # S: Инкассация
                20: f"{self._fmt_money(cash_remainder)} ₽"  # T: Остаток с ₽
            }

            # Обновляем каждую ячейку
            for col, value in updates.items():
                self.sheet.update_cell(row_idx, col, value)

            logger.info(f"✅ Строка {row_idx} обновлена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка обновления строки {row_idx}: {e}")
            return False

    def _append_new_row(self, date: str, shift: str, name: str, data: POSReport) -> bool:
        """Добавляет новую строку (если не найдена существующая)"""
        try:
            def to_float(val: Optional[str]) -> float:
                if not val:
                    return 0.0
                try:
                    return float(str(val).replace(" ", "").replace(",", "."))
                except (ValueError, TypeError):
                    return 0.0

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

            # Расчёты
            sbp_plus_beznal = sbp + cashless
            acquiring_commission = acquiring * 0.025
            acquiring_to_bank = acquiring - acquiring_commission
            pct_acquiring = (acquiring_commission / acquiring * 100) if acquiring > 0 else 0
            pct_sbp = (sbp / total * 100) if total > 0 else 0

            # Формируем полную строку (20 колонок)
            row = [
                date,  # A: Дата
                shift,  # B: Смена
                name,  # C: Администратор
                self._fmt_money(data.total),  # D: Z-отчет
                self._fmt_game_time(data.game_time),  # E: Игровое время + PS
                self._fmt_money(data.smoke),  # F: Кальян
                self._fmt_money(data.bar),  # G: бар
                self._fmt_money(data.cash),  # H: нал
                f"р.{self._fmt_money(sbp_plus_beznal)}",  # I: СБП+БЕЗНАЛ
                self._fmt_money(data.sbp),  # J: СБП
                self._fmt_money(data.acquiring),  # K: Эквайринг
                "",  # L: Равно?
                self._fmt_money(acquiring_to_bank),  # M: ЭКВАЙРИНГ! в банк
                f"{pct_acquiring:.2f}".replace(".", ","),  # N: % эвк
                f"{pct_sbp:.2f}".replace(".", ","),  # O: % сбп
                self._fmt_money(data.expense),  # P: Расход
                self._fmt_money(data.return_cashless),  # Q: Возврат безнал
                self._fmt_money(data.return_cash),  # R: Возврат нал
                "",  # S: Инкассация
                f"{self._fmt_money(cash_remainder)} ₽"  # T: Остаток с ₽
            ]

            self.sheet.append_row(row)
            logger.info(f"✅ Добавлена новая строка: {date} | {shift} | {name}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления строки: {e}")
            return False

    def append_report(self, name: str, date: str, shift: str, data: POSReport):
        """
        Главная логика:
        1. Ищем строку по дате и смене
        2. Если нашли - обновляем
        3. Если не нашли - добавляем новую
        """
        # Ищем существующую строку (теперь без name)
        row_idx = self._find_row(date, shift)

        if row_idx:
            # Обновляем найденную строку
            success = self._update_row(row_idx, data, shift)
        else:
            # Добавляем новую строку
            success = self._append_new_row(date, shift, name, data)

        if not success:
            raise Exception("Не удалось сохранить отчёт в таблицу")