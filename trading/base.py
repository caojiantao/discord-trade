from abc import ABC, abstractmethod

from parsers.models import TradeSignal

from .models import TradeOrderPlan


class TradeExecutor(ABC):
    def __init__(self, symbol_mapping: dict[str, str]):
        # 解析器保留原始品种名称；下单前转换成交易所实际 symbol。
        # 配置统一使用大写英文键；中文别名经过 upper() 后保持不变。
        self.symbol_mapping = {key.upper(): value for key, value in symbol_mapping.items()}

    def map_symbol(self, symbol: str) -> str:
        # 先规范化信号，再查映射；没有别名映射时直接使用大写后的原名称。
        normalized_symbol = symbol.upper()
        return self.symbol_mapping.get(normalized_symbol, normalized_symbol)

    @abstractmethod
    def build_plan(self, signal: TradeSignal) -> TradeOrderPlan | None:
        """把解析信号转换成订单计划；第一版不在这里直接请求交易所。"""
        raise NotImplementedError
