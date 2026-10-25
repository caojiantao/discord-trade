import unittest
from decimal import Decimal
from datetime import datetime, timezone

from parsers.models import Direction, TradeSignal
from trading.cfd import CfdExecutor
from trading.futures import FuturesExecutor


class TradingPlanTest(unittest.TestCase):
    def setUp(self):
        self.time = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.mapping = {"比特币": "BTC", "GOLD": "XAU"}

    def signal(self, symbol, direction=Direction.LONG):
        return TradeSignal(self.time, symbol, (Decimal("80000"), Decimal("80500")), direction,
                            (Decimal("82000"), Decimal("84000")), Decimal("79000"), "source")

    def test_futures_splits_fixed_notional_into_limit_orders(self):
        plan = FuturesExecutor(self.mapping, Decimal("1000")).build_plan(self.signal("比特币"))
        self.assertEqual(plan.market, "futures")
        self.assertEqual(plan.orders[0].symbol, "BTCUSDT")
        self.assertEqual([o.order_type for o in plan.orders], ["limit", "limit"])
        self.assertEqual([o.quantity for o in plan.orders], [Decimal("0.00625"), Decimal("0.006211180124223602484472049689")])
        self.assertEqual(plan.orders[0].take_profit, Decimal("82000"))

    def test_symbol_is_normalized_before_mapping(self):
        plan = FuturesExecutor(self.mapping, Decimal("1000")).build_plan(self.signal("btc"))
        self.assertEqual(plan.orders[0].symbol, "BTCUSDT")

    def test_cfd_market_or_limit_by_price_distance(self):
        parser = CfdExecutor(self.mapping, Decimal("0.01"), Decimal("3"), lambda _: Decimal("4028"))
        signal = TradeSignal(self.time, "GOLD", (Decimal("4026"),), Direction.LONG,
                             (Decimal("4040"),), Decimal("4018"), "source")
        plan = parser.build_plan(signal)
        self.assertEqual(plan.orders[0].symbol, "XAUUSD.s")
        self.assertEqual(plan.orders[0].order_type, "market")
        parser = CfdExecutor(self.mapping, Decimal("0.01"), Decimal("3"), lambda _: Decimal("4030"))
        self.assertEqual(parser.build_plan(signal).orders[0].order_type, "limit")

    def test_cfd_skips_non_gold_symbols(self):
        parser = CfdExecutor(self.mapping, Decimal("0.01"), price_provider=lambda _: Decimal("1"))
        signal = self.signal("比特币")
        self.assertIsNone(parser.build_plan(signal))


if __name__ == "__main__":
    unittest.main()
