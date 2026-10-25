import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from parsers.implementations.channel_1464406516282167448 import Channel1464406516282167448Parser


class Channel1464406516282167448ParserTest(unittest.TestCase):
    def test_real_messages(self):
        parser = Channel1464406516282167448Parser()
        path = Path(__file__).parent / "fixtures" / "channel_1464406516282167448.json"
        time = datetime(2026, 10, 24, tzinfo=timezone.utc)
        for sample in json.loads(path.read_text(encoding="utf-8")):
            with self.subTest(source_id=sample["id"]):
                if sample.get("error"):
                    with self.assertRaisesRegex(ValueError, "^解析价格异常$"):
                        parser.parse(sample["content"], signal_time=time, source_id=sample["id"])
                    continue
                result = parser.parse(sample["content"], signal_time=time, source_id=sample["id"])
                expected = sample["expected"]
                if expected is None:
                    self.assertIsNone(result)
                    continue
                self.assertEqual(result.symbol, expected["symbol"])
                self.assertEqual(result.direction.value, expected["direction"])
                self.assertEqual(result.entry_prices, tuple(map(Decimal, expected["entry_prices"])))
                self.assertEqual(result.take_profits, tuple(map(Decimal, expected["take_profits"])))
                self.assertEqual(result.stop_loss, Decimal(expected["stop_loss"]))
                self.assertEqual(result.signal_time, time)
                self.assertEqual(result.source_id, sample["id"])


if __name__ == "__main__":
    unittest.main()
