import csv
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from parsers.implementations.channel_1386949813743915029 import Channel1386949813743915029Parser


class Channel1386949813743915029ParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = Channel1386949813743915029Parser()
        self.time = datetime(2026, 10, 24, tzinfo=timezone.utc)
        paths = (Path(__file__).parent.parent / "csv" / "1386949813743915029").glob("*.csv")
        self.messages = {}
        for path in paths:
            with path.open(encoding="utf-8-sig", newline="") as file:
                self.messages.update({row["id"]: row["content"] for row in csv.DictReader(file)})

    def parse(self, source_id):
        return self.parser.parse(self.messages[source_id], signal_time=self.time, source_id=source_id)

    def test_real_long_signal(self):
        result = self.parse("1559926456874696736")
        self.assertEqual(result.symbol, "BTC")
        self.assertEqual(result.direction.value, "long")
        self.assertEqual(result.entry_prices, (Decimal("81700"), Decimal("82100")))
        self.assertEqual(result.take_profits, tuple(map(Decimal, (83500, 84900, 86600))))
        self.assertEqual(result.stop_loss, Decimal("80200"))
        self.assertEqual(result.source_id, "1559926456874696736")
        self.assertEqual(result.signal_time, self.time)

    def test_reply_can_contain_new_signal(self):
        result = self.parse("1551782948016103477")
        self.assertEqual(result.entry_prices, (Decimal("85200"), Decimal("85600")))

    def test_decimal_short_and_additional_entry(self):
        result = self.parse("1537376307917234226")
        self.assertEqual(result.symbol, "JTO")
        self.assertEqual(result.direction.value, "short")
        self.assertEqual(result.entry_prices, (Decimal("0.58"), Decimal("0.59")))
        self.assertEqual(result.take_profits, (Decimal("0.54"), Decimal("0.49")))
        self.assertEqual(result.stop_loss, Decimal("0.62"))
        result = self.parse("1518498457713643603")
        self.assertEqual(result.entry_prices, (Decimal("64250"), Decimal("65000")))

    def test_notifications_and_incomplete_corrections_are_ignored(self):
        for source_id in ("1563034696391065721", "1563015233973264385", "1559907004062109757"):
            with self.subTest(source_id=source_id):
                self.assertIsNone(self.parse(source_id))

    def test_invalid_price_order_raises(self):
        # 原文入场 60900-91300，而 TP1 为 62400，不能自行修正 91300。
        for source_id in ("1533735956341854330", "1563014020980678698", "1562421712321249352",
                          "1431989441215332527"):
            with self.subTest(source_id=source_id):
                with self.assertRaisesRegex(ValueError, "^解析价格异常$"):
                    self.parse(source_id)


if __name__ == "__main__":
    unittest.main()
