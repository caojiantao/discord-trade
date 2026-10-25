from decimal import Decimal
from collections.abc import Callable

from parsers.models import Direction, TradeSignal

from .base import TradeExecutor
from .models import EntryOrderPlan, TradeOrderPlan


class CfdExecutor(TradeExecutor):
    """CFD 执行器：接近入场价时市价，否则按信号价格限价。"""

    def __init__(
        self,
        symbol_mapping: dict[str, str],
        lots: Decimal,
        market_threshold: Decimal = Decimal("3"),
        price_provider: Callable[[str], Decimal] | None = None,
    ):
        super().__init__(symbol_mapping)
        self.lots = lots
        self.market_threshold = market_threshold
        self.price_provider = price_provider

    def build_plan(self, signal: TradeSignal) -> TradeOrderPlan | None:
        # 当前普通 CFD 账户是零手续费模式，Bitget 黄金品种使用 XAUUSD.s。
        mapped_symbol = self.map_symbol(signal.symbol)
        # CFD 第一版只处理黄金，其他外汇品种先跳过。
        base_symbol = mapped_symbol.removesuffix("USD")
        if base_symbol != "XAU":
            return None
        # 去掉已有 USD 后缀后统一生成 XAUUSD.s，避免重复出现 USD。
        symbol = f"{base_symbol}USD.s"
        if self.price_provider is None:
            raise RuntimeError("CFD 执行器未配置行情查询器")
        # 执行器自己查询当前价，调用方只传入解析后的信号。
        current_price = self.price_provider(symbol)
        # 做多开仓买入，做空开仓卖出。
        side = "buy" if signal.direction == Direction.LONG else "sell"
        orders = []
        for entry in signal.entry_prices:
            # 当前价距离信号入场价不超过阈值时追市价，否则挂回原入场价。
            is_market = abs(current_price - entry) <= self.market_threshold
            orders.append(EntryOrderPlan(
                symbol=symbol,
                order_type="market" if is_market else "limit",
                side=side,
                # CFD 第一版每个入场点固定下单手数。
                quantity=self.lots,
                price=None if is_market else entry,
                # 止损沿用信号；多个 TP 只使用第一个目标全平。
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profits[0],
                source_id=signal.source_id,
            ))
        return TradeOrderPlan(market="cfd", orders=tuple(orders))
