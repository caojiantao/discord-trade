"""将持久化的信号恢复成实体，并按频道构建交易计划。"""

import json
from datetime import datetime
from decimal import Decimal

from parsers.models import Direction, TradeSignal
from .cfd import CfdExecutor
from .futures import FuturesExecutor


def build_order_plan(row: dict, channel_config: dict, mapping: dict, client):
    # 旧的纯交互测试即使频道相同，也不能被新版确认按钮用于实盘交易。
    data = json.loads(row["signal_json"])
    if data["source_id"].startswith("urn:discord-trade:test:"):
        raise ValueError("此卡片仅用于交互测试，请忽略并发送新的实盘示例卡片")
    signal = TradeSignal(
        datetime.fromisoformat(data["signal_time"]), data["symbol"],
        tuple(Decimal(price) for price in data["entry_prices"]), Direction(data["direction"]),
        tuple(Decimal(price) for price in data["take_profits"]), Decimal(data["stop_loss"]),
        data["source_id"],
    )
    channel_id = row["channel_id"]
    settings = channel_config.get(channel_id) or channel_config.get(
        int(channel_id) if channel_id and channel_id.isdigit() else channel_id)
    if not settings:
        raise ValueError(f"频道未配置交易参数：{channel_id}")
    if settings["executor"] == "futures":
        return FuturesExecutor(mapping, Decimal(settings["notional_usdt"])).build_plan(signal)
    if settings["executor"] == "cfd":
        def current_price(symbol):
            tickers = client.get_cfd_ticker(symbol).get("data") or []
            ticker = next((item for item in tickers if item["symbol"] == symbol), None)
            if ticker is None:
                raise ValueError(f"未查询到 CFD 行情：{symbol}")
            # 买入看卖一，卖出看买一；在点击确认后查询，避免沿用发送卡片时的价格。
            return Decimal(ticker["ask1" if signal.direction == Direction.LONG else "bid1"])
        plan = CfdExecutor(mapping, Decimal(settings["lots"]),
                           Decimal(settings["threshold"]), current_price).build_plan(signal)
        if plan is None:
            raise ValueError(f"暂不支持此 CFD 品种：{signal.symbol}")
        return plan
    raise ValueError(f"未知交易执行器：{settings['executor']}")
