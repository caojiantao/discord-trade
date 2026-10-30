from decimal import Decimal

from parsers.models import Direction, TradeSignal

from .base import TradeExecutor
from .models import EntryOrderPlan, TradeOrderPlan


class FuturesExecutor(TradeExecutor):
    """合约执行器：所有入场点都使用限价单。"""

    def __init__(self, symbol_mapping: dict[str, str], max_loss_usdt: Decimal):
        super().__init__(symbol_mapping)
        self.max_loss_usdt = max_loss_usdt

    def build_plan(self, signal: TradeSignal) -> TradeOrderPlan:
        # Bitget USDT 永续合约直接使用 BTCUSDT、ETHUSDT 这类 symbol。
        symbol = f"{self.map_symbol(signal.symbol)}USDT"
        # 做多开仓是买入，做空开仓是卖出。
        side = "buy" if signal.direction == Direction.LONG else "sell"
        # 一个信号共用总止损预算，按各入场点到止损的距离分配风险。
        entry_count = len(signal.entry_prices)
        if self.max_loss_usdt <= 0 or not entry_count:
            raise ValueError("止损预算必须大于零，且至少有一个入场点")
        if any((entry <= signal.stop_loss if signal.direction == Direction.LONG
                else entry >= signal.stop_loss) for entry in signal.entry_prices):
            raise ValueError("止损价格方向异常")
        # 距离越远，分配的止损金额越大；等价于每个入场点下相同数量。
        total_distance = sum(abs(entry - signal.stop_loss) for entry in signal.entry_prices)
        quantity = self.max_loss_usdt / total_distance
        orders = tuple(
            EntryOrderPlan(
                symbol=symbol,
                # 合约频道第一版统一挂限价单。
                order_type="limit",
                side=side,
                # 全部入场成交时，总理论亏损为配置预算；不含手续费、滑点。
                quantity=quantity,
                price=entry,
                # 每笔订单沿用同一止损，止盈只使用 TP1 做全平。
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profits[0],
                source_id=signal.source_id,
            )
            for entry in signal.entry_prices
        )
        return TradeOrderPlan(market="futures", orders=orders)
