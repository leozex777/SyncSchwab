
# entities.py
# app.models.copier.entities

from __future__ import annotations

from dataclasses import dataclass, asdict
from app.core.logger import logger
from typing import Any, Dict, List, Literal, Optional


# ---------------- Instrument ----------------
@dataclass
class Instrument:
    """
    Базовое описание инструмента Schwab.
    """

    symbol: str                                  # "AAPL", "QLD", ...
    description: str                             # "Apple Inc", "PROSHARES ULTRA QQQ ETF"
    asset_type: str                              # Schwab: "EQUITY", "COLLECTIVE_INVESTMENT", ...
    security_type: Optional[str] = None          # Schwab: "EXCHANGE_TRADED_FUND", "STOCK", ...
    cusip: Optional[str] = None                  # "74347R206"

    @classmethod
    def from_schwab(cls, data: Dict[str, Any]) -> Instrument:
        return cls(
            symbol=data.get("symbol", ""),
            description=data.get("description", ""),
            asset_type=data.get("assetType", ""),
            security_type=data.get("type"),
            cusip=data.get("cusip"),
        )

    # --- Удобные свойства для ETF / акции ---

    @property
    def is_etf(self) -> bool:
        """
        ETF (в Schwab это обычно assetType="COLLECTIVE_INVESTMENT"
        и/или type="EXCHANGE_TRADED_FUND").
        """
        return (
                self.asset_type == "COLLECTIVE_INVESTMENT"
                or self.security_type == "EXCHANGE_TRADED_FUND"
        )

    @property
    def is_equity(self) -> bool:
        """
        Обычная акция (assetType="EQUITY").
        """
        return self.asset_type == "EQUITY"

    @property
    def asset_kind(self) -> str:
        """
        Удобное «человеческое» обозначение типа:
        "ETF", "STOCK" или "OTHER".
        """
        if self.is_etf:
            return "ETF"
        if self.is_equity:
            return "STOCK"
        return "OTHER"


# ---------------- Position ----------------

@dataclass
class Position:
    """
    Позиция по инструменту на счёте.
    Поддерживает:
      - ETF long/short
      - акции long/short
    """

    account_number: str
    instrument: Instrument

    side: Literal["LONG", "SHORT"]  # направление позиции
    quantity: float  # всегда >= 0
    average_price: float
    market_value: float
    unrealized_pl: float
    maintenance_requirement: float

    # ---------- Удобные свойства ----------

    @property
    def symbol(self) -> str:
        return self.instrument.symbol

    @property
    def cusip(self) -> Optional[str]:
        return self.instrument.cusip

    @property
    def asset_type(self) -> str:
        return self.instrument.asset_type

    @property
    def is_long(self) -> bool:
        return self.side == "LONG"

    @property
    def is_short(self) -> bool:
        return self.side == "SHORT"

    @property
    def is_etf(self) -> bool:
        return self.instrument.is_etf

    @property
    def is_stock(self) -> bool:
        return self.instrument.is_equity

    @property
    def asset_kind(self) -> str:
        """
        "ETF", "STOCK" или "OTHER" — для логики копировщика.
        """
        return self.instrument.asset_kind

    @property
    def notional(self) -> float:
        """
        Номинал позиции (quantity * average_price).
        """
        return self.quantity * self.average_price

    # ---------- Фабрика из Schwab JSON ----------

    @classmethod
    def from_schwab_position(
            cls,
            account_number: str,
            data: Dict[str, Any],
    ) -> Position:
        """
        data — один элемент из массива "positions".
        """
        long_q = float(data.get("longQuantity", 0.0) or 0.0)
        short_q = float(data.get("shortQuantity", 0.0) or 0.0)

        if long_q == 0.0 and short_q == 0.0:
            raise ValueError("Empty Schwab position: both longQuantity and shortQuantity are 0")

        if long_q > 0.0 and short_q > 0.0:
            net = long_q - short_q
            if net >= 0:
                side: Literal["LONG", "SHORT"] = "LONG"
                quantity = net
            else:
                side = "SHORT"
                quantity = -net
        elif long_q > 0.0:
            side = "LONG"
            quantity = long_q
        else:
            side = "SHORT"
            quantity = short_q

        instrument_raw = data.get("instrument", {}) or {}
        instrument = Instrument.from_schwab(instrument_raw)

        avg_price = float(
            data.get("averagePrice")
            or data.get("averageLongPrice")
            or data.get("averageShortPrice")
            or 0.0
        )

        market_value = float(data.get("marketValue", 0.0) or 0.0)

        unrealized_pl = float(
            data.get("longOpenProfitLoss")
            or data.get("shortOpenProfitLoss")
            or data.get("currentDayProfitLoss")
            or 0.0
        )

        maintenance_req = float(data.get("maintenanceRequirement", 0.0) or 0.0)

        return cls(
            account_number=account_number,
            instrument=instrument,
            side=side,
            quantity=quantity,
            average_price=avg_price,
            market_value=market_value,
            unrealized_pl=unrealized_pl,
            maintenance_requirement=maintenance_req,
        )


# ------------------------------------------------------------
# Парсер всего accountDetails / accountDetailsAll
# ------------------------------------------------------------

def parse_positions_from_account_details(details: Dict[str, Any]) -> List[Position]:
    """
    Преобразует Schwab-ответ accountDetails в список Position

    Args:
        details: Ответ от API account_details

    Returns:
        Список позиций
    """
    sa = details.get("securitiesAccount", {}) or {}
    account_number = sa.get("accountNumber", "")
    raw_positions = sa.get("positions", []) or []

    result: List[Position] = []

    for p in raw_positions:
        try:
            pos = Position.from_schwab_position(account_number, p)
        except ValueError as e:
            # Пустые или некорректные позиции пропускаем
            logger.debug(f"Skipping invalid position: {e}")
            continue
        else:
            result.append(pos)

    return result


def fetch_and_save_positions(hash_account: str) -> List[Position]:
    """
    - Делает запрос client.account_details(...)
    - Извлекает позиции
    - Преобразует в List[Position]
    - Сохраняет в JSON в виде list[dict]
    - Печатает позиции красиво
    - Возвращает список Position
    """
    from app.core.config import get_main_client, get_account_number_by_hash
    from app.core.paths import DATA_DIR
    from app.core.json_utils import save_json

    client = get_main_client()

    if not client:
        # Логировать ошибку (НЕ использовать streamlit!)
        logger.error("Main account not authorized - cannot fetch positions")
        return []  # ← Вернуть пустой список

    # Получить номер аккаунта по hash
    name_account = get_account_number_by_hash(client, hash_account)

    if not name_account:
        logger.error(f"Account not found for hash: {hash_account[:3]}...{hash_account[-3:]}")
        return []

    file_path: str = str(DATA_DIR / f"{name_account}_positions.json")

    logger.info(f"Запрос позиций Schwab для {name_account} ...")

    try:
        # 1. Получаем детали аккаунта
        details = client.account_details(hash_account, fields="positions").json()

        # 2. Парсим в Position
        positions: List[Position] = parse_positions_from_account_details(details)
        logger.info(f"Парсер нашёл позиций: {len(positions)}")

        # 3. Печать всех позиций
        for i, pos in enumerate(positions, start=1):
            print(f"\n────────── Позиция #{i} ──────────")
            from pprint import pprint
            pprint(asdict(pos))

        # 4. Сохраняем в файл как список словарей
        dict_list = [asdict(p) for p in positions]
        save_json(file_path, dict_list)

        logger.info(f"Позиции сохранены в файл: {name_account}_positions.json")

        return positions

    except Exception as e:
        logger.error(f"Failed to fetch positions for {name_account}: {e}")
        return []
