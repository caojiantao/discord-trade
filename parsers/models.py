from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Direction(str, Enum):
    """限定多空取值；继承 str，便于输出为 JSON 字符串。"""
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class TradeSignal:
    """统一的开仓信号；dataclass 自动生成构造方法等，frozen 禁止字段重新赋值。"""

    signal_time: datetime  # 信号时间；使用北京时间（Asia/Shanghai），带时区。
    symbol: str  # 交易对，例如 BTCUSDT。
    # Decimal 用于十进制价格，避免 float 的二进制表示误差。
    # tuple[Decimal, ...] 表示可包含多个价格；区间与分批入场由解析规则约定。
    entry_prices: tuple[Decimal, ...]
    direction: Direction  # long 做多，short 做空。
    take_profits: tuple[Decimal, ...]  # 按消息中的顺序保存多个止盈价。
    stop_loss: Decimal  # 止损价；当前 1295531142912413852 频道提取的是模糊描述中的参考边界。
    source_id: str  # 原消息标识，用于溯源；由调用方传入，不从正文猜测。
