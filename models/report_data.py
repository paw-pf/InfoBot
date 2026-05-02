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
    return_cash: Optional[str] = None
    return_cashless: Optional[str] = None

    # Новые поля для ручного ввода (кассовые операции)
    returns: Optional[str] = None  # 🔁 Возвраты (общая сумма)
    exchange: Optional[str] = None  # 💱 Размен в кассе
    envelope: Optional[str] = None  # 📬 В конверте
    expense: Optional[str] = None  # 📉 Расход

    # Мета-поля (не сохраняются в таблицу, только для отчёта)
    name: Optional[str] = None
    date: Optional[str] = None
    shift: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Конвертирует в словарь для Google Sheets (только табличные поля)"""
        return {
            # Основные
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
            # Кассовые операции (новые)
            "returns": self.returns,
            "exchange": self.exchange,
            "envelope": self.envelope,
            "expense": self.expense,
        }

    def to_report_dict(self) -> Dict[str, str]:
        """Словарь для формирования текста отчёта (с дефолтными значениями)"""
        return {
            "total": self.total or "0",
            "game_time": self.game_time or "0",
            "bar": self.bar or "0",
            "cash": self.cash or "0",
            "cashless": self.cashless or "0",
            "sbp": self.sbp or "0",
            "acquiring": self.acquiring or "0",
            "services": self.services or "0",
            "return_cash": self.return_cash or "0",
            "return_cashless": self.return_cashless or "0",
            "returns": self.returns or "0",
            "exchange": self.exchange or "0",
            "envelope": self.envelope or "0",
            "expense": self.expense or "0",
            "name": self.name or "Неизвестно",
            "date": self.date or "",
            "shift": self.shift or "День",
        }

    @classmethod
    def from_user_input(cls, user_data: Dict[str, str]) -> "POSReport":
        """Создаёт POSReport из данных, введённых пользователем"""
        # Вычисляем производные значения
        cash = int(user_data.get("cash", 0) or 0)
        sbp = int(user_data.get("sbp", 0) or 0)
        acquiring = int(user_data.get("acquiring", 0) or 0)
        bar = int(user_data.get("bar", 0) or 0)
        services = int(user_data.get("services", 0) or 0)

        return cls(
            # Вычисляемые
            total=str(cash + sbp + acquiring),
            game_time=str(bar + services),
            cashless=str(sbp + acquiring),
            # Прямые значения
            cash=str(cash),
            sbp=str(sbp),
            acquiring=str(acquiring),
            bar=str(bar),
            services=str(services),
            return_cash=user_data.get("returns", "0"),  # Возвраты мапим на return_cash
            return_cashless="0",
            # Новые кассовые поля
            returns=user_data.get("returns", "0"),
            exchange=user_data.get("exchange", "0"),
            envelope=user_data.get("envelope", "0"),
            expense=user_data.get("expense", "0"),
            # Мета
            name=user_data.get("name"),
            date=user_data.get("date"),
            shift=user_data.get("shift"),
        )