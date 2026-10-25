from decimal import Decimal

from parsers.models import Direction, TradeSignal

from .base import TradeExecutor
from .models import EntryOrderPlan, TradeOrderPlan


class FuturesExecutor(TradeExecutor):
    """合约执行器：所有入场点都使用限价单。"""

    def __init__(self, symbol_mapping: dict[str, str], notional_usdt: Decimal):
        super().__init__(symbol_mapping)
        self.notional_usdt = notional_usdt

    def build_plan(self, signal: TradeSignal) -> TradeOrderPlan:
        # Bitget USDT 永续合约直接使用 BTCUSDT、ETHUSDT 这类 symbol。
        symbol = f"{self.map_symbol(signal.symbol)}USDT"
        # 做多开仓是买入，做空开仓是卖出。
        side = "buy" if signal.direction == Direction.LONG else "sell"
        # 固定名义金额平均分到多个入场点，不根据止损距离反推仓位。
        entry_count = len(signal.entry_prices)
        notional_each = self.notional_usdt / entry_count
        orders = tuple(
            EntryOrderPlan(
                symbol=symbol,
                # 合约频道第一版统一挂限价单。
                order_type="limit",
                side=side,
                # 数量 = 本笔名义金额 / 入场价格。
                quantity=notional_each / entry,
                price=entry,
                # 每笔订单沿用同一止损，止盈只使用 TP1 做全平。
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profits[0],
                source_id=signal.source_id,
            )
            for entry in signal.entry_prices
        )
        return TradeOrderPlan(market="futures", orders=orders)
