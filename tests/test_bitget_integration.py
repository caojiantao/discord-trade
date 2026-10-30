"""Bitget 实盘集成测试；默认跳过，避免普通测试意外下单。"""

import os
import unittest
import logging
from datetime import datetime, timezone
from decimal import Decimal

from config import app, credentials, trading as trading_config
from parsers.implementations.channel_1464406516282167448 import Channel1464406516282167448Parser
from parsers.implementations.channel_1488133240975003761 import Channel1488133240975003761Parser
from trading.bitget import BitgetClient
from trading.cfd import CfdExecutor
from trading.futures import FuturesExecutor


MESSAGE = (
    "Sol做多策略：100做多，止损94.5，目标一105.5，目标二待定。"
    "仅纪录个人观点和操作，不构成交易建议。"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@unittest.skipUnless(os.getenv("RUN_BITGET_INTEGRATION") == "1", "设置 RUN_BITGET_INTEGRATION=1 才执行 Bitget 下单测试")
class BitgetIntegrationTest(unittest.TestCase):
    def test_place_futures_order_from_discord_message(self):
        # 先复用真实频道解析器，确保测试下单使用的字段来自实际消息格式。
        signal = Channel1464406516282167448Parser().parse(
            MESSAGE,
            signal_time=datetime(2026, 10, 17, 16, 28, 35, tzinfo=timezone.utc),
            source_id="https://discord.com/channels/1295108691275813036/1464406516282167448/1561053322620829881",
        )
        self.assertIsNotNone(signal)
        # 止损预算 5.5 USDT，价差 5.5，对应 1 SOL（100 USDT 名义仓位）。
        plan = FuturesExecutor(trading_config.TRADE_SYMBOL_MAPPING, Decimal("5.5")).build_plan(signal)
        order = plan.orders[0]
        client = BitgetClient(
            credentials.BITGET_API_KEY,
            credentials.BITGET_API_SECRET,
            credentials.BITGET_API_PASSPHRASE,
            demo=credentials.BITGET_DEMO,
            proxy=app.HTTP_PROXY,
        )
        try:
            response = client.place_futures_order(order)
        except Exception:
            logging.exception("Bitget 下单异常")
            raise
        self.assertEqual(response.get("code"), "00000")

    def test_place_cfd_order_from_gold_message(self):
        """用黄金 CFD 示例消息测试一次入场、止盈和止损请求。"""
        message = """GOLD BUY NOW
@ 4538

TP : 4550
TP : 4570

SL : 4522"""
        # 先走真实频道解析器，确保交易请求使用解析后的结构化信号。
        signal = Channel1488133240975003761Parser().parse(
            message,
            signal_time=datetime(2026, 10, 25, 16, 40, tzinfo=timezone.utc),
            source_id="https://discord.com/channels/1295108691275813036/1488133240975003761/test-cfd",
        )
        self.assertIsNotNone(signal)
        # 示例入场价作为当前价，触发 CFD 执行器的市价逻辑；实际运行时这里应接行情查询。
        plan = CfdExecutor(
            trading_config.TRADE_SYMBOL_MAPPING,
            Decimal("0.01"),
            price_provider=lambda _: Decimal("4538"),
        ).build_plan(signal)
        self.assertIsNotNone(plan)
        order = plan.orders[0]
        self.assertEqual(order.symbol, "XAUUSD.s")
        self.assertEqual(order.order_type, "market")
        self.assertEqual(order.take_profit, Decimal("4550"))
        self.assertEqual(order.stop_loss, Decimal("4522"))

        client = BitgetClient(
            credentials.BITGET_API_KEY,
            credentials.BITGET_API_SECRET,
            credentials.BITGET_API_PASSPHRASE,
            demo=credentials.BITGET_DEMO,
            proxy=app.HTTP_PROXY,
        )
        try:
            response = client.place_cfd_order(order)
        except Exception:
            logging.exception("Bitget CFD 下单异常")
            raise
        self.assertEqual(response.get("code"), "00000")
