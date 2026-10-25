from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class EntryOrderPlan:
    """单个入场订单及其保护价格；只描述计划，不直接请求交易所。"""
    symbol: str
    order_type: Literal["market", "limit"]
    side: Literal["buy", "sell"]
    quantity: Decimal
    price: Decimal | None
    stop_loss: Decimal
    take_profit: Decimal
    source_id: str


@dataclass(frozen=True)
class TradeOrderPlan:
    """一个信号拆分出的完整订单计划。"""
    market: Literal["futures", "cfd"]
    orders: tuple[EntryOrderPlan, ...]
