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
            logger.info("Successfully authenticated with Google Sheets")
        except Exception as e:
            logger.error(f"Error authenticating with Google Sheets: {e}")
            raise

    @staticmethod
    def _format_num(value, decimals=2, prefix="", suffix=""):
        if decimals == 0:
            formatted = f"{value:,.0f}".replace(",", " ")
        else:
            formatted = f"{value:,.{decimals}f}"
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", " ")
        return f"{prefix}{formatted}{suffix}"

    def append_report(self, name: str, date: str, shift: str, data: POSReport):
        try:
            expected_headers = [
                "Дата", "Смена", "Администратор", "Z-отчет",
                "Игровое время + PS", "Кальян", "Бар", "Нал",
                "СБП+БЕЗНАЛ", "СБП", "Эквайринг", "Равно?",
                "ЭКВАЙРИНГ! в банк", "% экв", "% сбп", "Расход",
                "Возврат безнал", "Возврат нал", "Инкассация", "Примечание",
            ]

            # Check if headers exist and match expected
            current_headers = self.sheet.row_values(1)
            if current_headers != expected_headers:
                logger.info("Updating sheet headers to match expected format")
                self.sheet.clear()
                self.sheet.append_row(expected_headers)
                self.sheet.format("A1:T1", {"textFormat": {"bold": True}})

            # Parse numeric values
            total = float(data.total or 0)
            game_time = float(data.game_time or 0)
            bar = float(data.bar or 0)
            cash = float(data.cash or 0)
            cashless = float(data.cashless or 0)
            sbp = float(data.sbp or 0)
            acquiring = float(data.acquiring or 0)
            services = float(data.services or 0)
            return_cash = float(data.return_cash or 0)
            return_cashless = float(data.return_cashless or 0)
            cash_expense = float(data.cash_expense or 0)
            envelope = float(data.envelope or 0)
            cash_remainder = float(data.cash_remainder or 0)

            # Calculate derived fields
            sbp_plus_beznal = sbp + cashless
            acquiring_commission = acquiring * 0.025
            acquiring_to_bank = acquiring - acquiring_commission
            pct_acquiring = (acquiring / total * 100) if total > 0 else 0
            pct_sbp = (sbp / total * 100) if total > 0 else 0

            # Prepare row
            fmt = self._format_num
            row = [
                date, shift, name,
                fmt(total),
                f"р.{fmt(game_time, decimals=0)}",
                fmt(services),
                fmt(bar),
                fmt(cash),
                f"р.{fmt(sbp_plus_beznal)}",
                fmt(sbp),
                fmt(acquiring),
                "",  # Равно? — оставляем пустым
                fmt(acquiring_to_bank),
                fmt(pct_acquiring),
                fmt(pct_sbp),
                fmt(cash_expense),
                fmt(return_cashless),
                fmt(return_cash),
                fmt(envelope),
                "",  # Примечание — оставляем пустым
            ]

            self.sheet.append_row(row)
            logger.info(f"Successfully appended report for {name} on {date}")
        except Exception as e:
            logger.error(f"Error appending report to Google Sheets: {e}")
            raise
