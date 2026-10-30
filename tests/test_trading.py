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

    def test_futures_splits_loss_budget_into_limit_orders(self):
        plan = FuturesExecutor(self.mapping, Decimal("30")).build_plan(self.signal("比特币"))
        self.assertEqual(plan.market, "futures")
        self.assertEqual(plan.orders[0].symbol, "BTCUSDT")
        self.assertEqual([o.order_type for o in plan.orders], ["limit", "limit"])
        self.assertEqual([o.quantity for o in plan.orders], [Decimal("0.012"), Decimal("0.012")])
        self.assertEqual(sum(o.quantity * abs(o.price - o.stop_loss) for o in plan.orders), Decimal("30"))
        self.assertEqual(plan.orders[0].take_profit, Decimal("82000"))

    def test_short_loss_budget_and_invalid_stop(self):
        signal = TradeSignal(self.time, "SOL", (Decimal("100"), Decimal("102")), Direction.SHORT,
                             (Decimal("90"),), Decimal("110"), "source")
        plan = FuturesExecutor(self.mapping, Decimal("20")).build_plan(signal)
        self.assertEqual(plan.orders[0].quantity, Decimal("20") / Decimal("18"))
        self.assertEqual(plan.orders[0].quantity, plan.orders[1].quantity)
        with self.assertRaises(ValueError):
            FuturesExecutor(self.mapping, Decimal("20")).build_plan(self.signal("BTC", Direction.SHORT))

    def test_loss_is_allocated_by_entry_distance(self):
        signal = TradeSignal(self.time, "SOL", (Decimal("100"), Decimal("90")), Direction.LONG,
                             (Decimal("120"),), Decimal("70"), "source")
        plan = FuturesExecutor(self.mapping, Decimal("50")).build_plan(signal)
        self.assertEqual([o.quantity for o in plan.orders], [Decimal("1"), Decimal("1")])
        self.assertEqual([o.quantity * abs(o.price - o.stop_loss) for o in plan.orders],
                         [Decimal("30"), Decimal("20")])

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
