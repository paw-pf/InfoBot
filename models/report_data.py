from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class POSReport:
    """Модель отчёта с поддержкой ручного ввода и парсинга"""

    # Основные поля (из оригинального парсера)
    total: Optional[str] = None
    game_time: Optional[str] = None
    bar: Optional[str] = None
    cash: Optional[str] = None
    cashless: Optional[str] = None
    sbp: Optional[str] = None
    acquiring: Optional[str] = None
    services: Optional[str] = None
    smoke: Optional[str] = None  # 💭 Кальяны
    return_cash: Optional[str] = None
    return_cashless: Optional[str] = None
    cash_in: Optional[str] = None  # 📥 Приход
    expense: Optional[str] = None  # 📤 Расход
    envelope: Optional[str] = None  # 📬 В конверт
    cash_remainder: Optional[str] = None  # 🏦 Остаток

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Конвертирует в словарь для Google Sheets (только табличные поля)"""
        return {
            "total": self.total,
            "game_time": self.game_time,
            "bar": self.bar,
            "cash": self.cash,
            "cashless": self.cashless,
            "sbp": self.sbp,
            "acquiring": self.acquiring,
            "services": self.services,
            "smoke": self.smoke,
            "return_cash": self.return_cash,
            "return_cashless": self.return_cashless,
            "cash_in": self.cash_in,
            "expense": self.expense,
            "envelope": self.envelope,
            "cash_remainder": self.cash_remainder,
            "receiver": self.receiver,
        }