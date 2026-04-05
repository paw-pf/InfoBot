from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class POSReport:
    total: Optional[str] = None
    game_time: Optional[str] = None
    bar: Optional[str] = None
    cash: Optional[str] = None
    cashless: Optional[str] = None
    sbp: Optional[str] = None
    acquiring: Optional[str] = None
    services: Optional[str] = None
    return_cash: Optional[str] = None
    return_cashless: Optional[str] = None
    cash_income: Optional[str] = None
    cash_expense: Optional[str] = None
    envelope: Optional[str] = None
    cash_remainder: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "total": self.total,
            "game_time": self.game_time,
            "bar": self.bar,
            "cash": self.cash,
            "cashless": self.cashless,
            "sbp": self.sbp,
            "acquiring": self.acquiring,
            "services": self.services,
            "return_cash": self.return_cash,
            "return_cashless": self.return_cashless,
            "cash_income": self.cash_income,
            "cash_expense": self.cash_expense,
            "envelope": self.envelope,
            "cash_remainder": self.cash_remainder,
        }
