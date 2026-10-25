import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from parsers.implementations.channel_1488133240975003761 import Channel1488133240975003761Parser


class Channel1488133240975003761ParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = Channel1488133240975003761Parser()
        self.time = datetime(2026, 10, 24, tzinfo=timezone.utc)

    def test_exported_messages(self):
        # 从原始 CSV 摘取固定样本，测试不依赖完整导出目录或网络。
        path = Path(__file__).parent / "fixtures" / "channel_1488133240975003761.json"
        for sample in json.loads(path.read_text()):
            # 同时验证 CSV 的字面量换行与 Discord 的真实换行。
            for content in (sample["content"], sample["content"].replace("\\n", "\n")):
                with self.subTest(message_id=sample["id"], content=content):
                    if sample.get("error"):
                        with self.assertRaisesRegex(ValueError, sample["error"]):
                            self.parser.parse(content, signal_time=self.time, source_id=sample["id"])
                        continue
                    result = self.parser.parse(content, signal_time=self.time, source_id=sample["id"])
                    expected = sample["expected"]
                    if expected is None:
                        self.assertIsNone(result)
                        continue
                    self.assertIsNotNone(result)
                    symbol, side, entries, targets, stop = expected
                    self.assertEqual(result.symbol, symbol)
                    self.assertEqual(result.direction.value, side)
                    self.assertEqual(result.entry_prices, tuple(map(Decimal, entries)))
                    self.assertEqual(result.take_profits, tuple(map(Decimal, targets)))
                    self.assertEqual(result.stop_loss, Decimal(stop))
                    self.assertEqual(result.signal_time, self.time)
                    self.assertEqual(result.source_id, sample["id"])

    def test_symbol_is_not_restricted_to_gold_or_forex(self):
        for symbol in ("GOLD", "EURUSD", "BTCUSDT", "XAGUSD", "US30", "BTC/USDT"):
            with self.subTest(symbol=symbol):
                content = f"{symbol} BUY NOW\n@ 4000\nTP: 4020\nSL: 3990"
                result = self.parser.parse(content, signal_time=self.time, source_id="symbol")
                self.assertIsNotNone(result)
                self.assertEqual(result.symbol, symbol)

    def test_entry_range_is_equivalent_to_more(self):
        for side, first, second, targets, stop in [
            ("BUY", "4378", "4368", ("4390", "4406"), "4358"),
            ("SELL", "4368", "4378", ("4350", "4340"), "4388"),
        ]:
            with self.subTest(side=side):
                suffix = f"\nTP: {targets[0]}\nTP: {targets[1]}\nSL: {stop}"
                messages = [f"GOLD {side} NOW\n@ {first} - {second}" + suffix,
                            f"GOLD {side} NOW\n@ {first}\nMORE {side} @ {second}" + suffix]
                signals = [self.parser.parse(content, signal_time=self.time, source_id="range")
                           for content in messages]
                self.assertIsNotNone(signals[0])
                self.assertEqual(signals[0], signals[1])

    def test_price_chain_order(self):
        for side, entries, targets, stop in [
            ("BUY", "4000\nMORE BUY @ 3995", ("4020", "4030"), "3990"),
            ("SELL", "4000\nMORE SELL @ 4005", ("3980", "3970"), "4010"),
        ]:
            for prices, valid in [(targets, True), (targets[::-1], False),
                                  ((targets[0], targets[0]), False),
                                  (("4000", targets[1]), False)]:
                with self.subTest(side=side, targets=prices):
                    content = (f"GOLD {side} NOW\n@ {entries}\n"
                               f"TP: {prices[0]}\nTP: {prices[1]}\nSL: {stop}")
                    if valid:
                        result = self.parser.parse(content, signal_time=self.time, source_id="order")
                        self.assertIsNotNone(result)
                        self.assertEqual(result.take_profits, tuple(map(Decimal, targets)))
                    else:
                        with self.assertRaisesRegex(ValueError, "解析价格异常"):
                            self.parser.parse(content, signal_time=self.time, source_id="order")

    def test_only_price_order_is_validated(self):
        valid = "GOLD BUY NOW\n@ 4000\nTP: 4020\nSL: 3990"
        # MORE 的 BUY/SELL 不参与校验；价格为零也仅按顺序判断。
        for content in [valid + "\nMORE SELL @ 3995",
                        valid.replace("SL: 3990", "SL: 0")]:
            with self.subTest(content=content):
                self.assertIsNotNone(self.parser.parse(content, signal_time=self.time, source_id="valid"))
        for content in [valid.replace("@ 4000", "@ 0"),
                        valid.replace("SL: 3990", "SL: 4010")]:
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, "解析价格异常"):
                    self.parser.parse(content, signal_time=self.time, source_id="invalid")

    def test_reversed_entry_order_raises(self):
        for side, entries, targets, stop in [
            ("BUY", ("3995", "4000"), ("4020", "4030"), "3990"),
            ("SELL", ("4005", "4000"), ("3980", "3970"), "4010"),
        ]:
            with self.subTest(side=side):
                content = (f"GOLD {side} NOW\n@ {entries[0]}\nMORE {side} @ {entries[1]}\n"
                           f"TP: {targets[0]}\nTP: {targets[1]}\nSL: {stop}")
                with self.assertRaisesRegex(ValueError, "解析价格异常"):
                    self.parser.parse(content, signal_time=self.time, source_id="entry-order")

    def test_incomplete_or_ambiguous_messages(self):
        valid = "GOLD BUY NOW\n@ 4000\nTP: 4020\nSL: 3990"
        invalid = ["", "[Photo]", valid.replace("TP: 4020", "TP: OPEN"),
                   valid + "\nSL: 3980", valid.replace("4020", "4020/4030 PIPS")]
        for content in invalid:
            with self.subTest(content=content):
                self.assertIsNone(self.parser.parse(content, signal_time=self.time, source_id="test"))


if __name__ == "__main__":
    unittest.main()
