import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from parsers.implementations.channel_1295531142912413852 import Channel1295531142912413852Parser


class Channel1295531142912413852ParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = Channel1295531142912413852Parser()
        self.time = datetime(2026, 10, 24, tzinfo=timezone.utc)

    def test_exported_messages(self):
        path = Path(__file__).parent / "fixtures" / "channel_1295531142912413852.json"
        expected = {
            "1561656659355369564": ("比特币", "short", (83900, 84400), (82900, 81900, 80800), 85000),
            "1559955428044185685": ("比特币", "long", (80000, 80800), (82300, 84000, 87000), 79000),
            "1555205496133390367": ("比特币", "long", (83000,), (84000, 85000, 87000), 82000),
            "1552983321477251155": ("ETH", "short", (2750, 2800), (2650, 2550, 2460), None),
            "1555164723409068184": ("原油CL", "short", (9500, 10000), (9100,), None),
            "1556998400690360403": ("SPCX", "short", (174, 180), (168, 158), 183),
        }
        for sample in json.loads(path.read_text()):
            with self.subTest(message_id=sample["id"]):
                result = self.parser.parse(sample["content"], signal_time=self.time, source_id=sample["id"])
                exp = expected[sample["id"]]
                if exp[-1] is None:
                    self.assertIsNone(result)
                    continue
                symbol, side, entries, targets, stop = exp
                self.assertEqual(result.symbol, symbol)
                self.assertEqual(result.direction.value, side)
                self.assertEqual(result.entry_prices, tuple(map(Decimal, entries)))
                self.assertEqual(result.take_profits, tuple(map(Decimal, targets)))
                self.assertEqual(result.stop_loss, Decimal(stop))
                self.assertEqual(result.source_id, sample["id"])

    def test_unit_inference_does_not_depend_on_symbol(self):
        for symbol in ("比特币", "BTC", "OTHER"):
            for suffix, multiplier in [("万", 10000), ("W", 10000), ("", 1)]:
                with self.subTest(symbol=symbol, unit=suffix):
                    content = (f"{symbol}\n方向：做多\n入场：8-8.08附近\n"
                               f"止盈：点位1：8.23附近 点位2：8.4{suffix}\n止损：小幅跌破7.9一点。")
                    result = self.parser.parse(content, signal_time=self.time, source_id="unit")
                    self.assertEqual(result.entry_prices, (Decimal('8') * multiplier, Decimal('8.08') * multiplier))
                    self.assertEqual(result.stop_loss, Decimal('7.9') * multiplier)

    def test_reply_without_new_signal_is_ignored(self):
        content = "> 回复 @舒琴操作日记VIP分享: [比特币 方向：做空]\n之前的单子盈利了。"
        self.assertIsNone(self.parser.parse(content, signal_time=self.time, source_id="reply"))


if __name__ == "__main__":
    unittest.main()
