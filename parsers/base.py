from abc import ABC, abstractmethod
from datetime import datetime

from .models import Direction, TradeSignal


class SignalParser(ABC):
    """类似 Java 接口：继承后必须实现 parse，才能创建解析器实例。"""

    @abstractmethod
    def parse(self, content: str, *, signal_time: datetime, source_id: str) -> TradeSignal | None:
        """输入正文和消息元数据，返回统一信号；非信号或字段不全时返回 None。

        * 后面的参数必须通过名称传递，避免时间和来源标识传错位置。
        接口独立于 Discord，其他消息平台也可调用。
        完整信号存在明显的语义错误时，解析器可抛出 ValueError。
        """
        raise NotImplementedError

    def _validate(self, signal: TradeSignal, *, reverse_long_entries: bool = False) -> None:
        """按原消息约定检查价格顺序，不符合时抛出异常。"""
        entries = signal.entry_prices
        if signal.direction == Direction.LONG:
            # 部分频道做多补仓价逐次降低，反转后检查从小到大的价格链。
            if reverse_long_entries:
                entries = tuple(reversed(entries))
            chain = [signal.stop_loss, *entries, *signal.take_profits]
        else:
            chain = [*reversed(signal.take_profits), *entries, signal.stop_loss]
        # 不排序，避免掩盖原消息中的价格顺序错误。
        if any(left >= right for left, right in zip(chain, chain[1:])):
            raise ValueError("解析价格异常")
