import tempfile
import json
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from notifications.confirmation import ConfirmationHandler
from parsers.models import Direction, TradeSignal
from storage.database import Database
from storage.models import DiscordMessage


class ConfirmationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / "db.sqlite3")
        self.db.save_signal("123", TradeSignal(
            datetime.now(timezone.utc), "GOLD", (Decimal("4538"),), Direction.LONG,
            (Decimal("4550"),), Decimal("4522"), "https://discord.com/channels/1/2/123"))
        self.handler = ConfirmationHandler(self.db, "ou_owner")
        self.addCleanup(self.handler.workers.shutdown)

    def event(self, action, operator="ou_owner"):
        return SimpleNamespace(event=SimpleNamespace(
            operator=SimpleNamespace(open_id=operator),
            action=SimpleNamespace(value={"action": action, "message_id": "123"})))

    def test_confirm_only_acknowledges_without_trading(self):
        response = self.handler.handle(self.event("confirm"))
        self.assertIn("交易开关未开启", response.toast.content)
        self.assertEqual(self.db.get_signal("123")["status"], "pending")

    def enable_sol(self):
        self.db.save_message(DiscordMessage(
            "123", "https://discord.com/channels/1/2/123", "test-sol", "test", "test",
            "Sol做多策略", [], [], None, datetime.now(timezone.utc)))
        # 本用例复用同一信号主键，写入 SOL 的实际解析结果。
        signal = TradeSignal(datetime.now(timezone.utc), "SOL", (Decimal("100"),), Direction.LONG,
                             (Decimal("105.5"),), Decimal("94.5"), "https://discord.com/channels/1/2/123")
        with self.db._connect() as connection:
            connection.execute("UPDATE trade_signals SET signal_json = ? WHERE message_id = '123'",
                               (json.dumps(asdict(signal), default=str),))
        self.handler.enabled = True
        self.handler.bitget = MagicMock()
        self.handler.bitget.place_futures_order.return_value = {"code": "00000", "data": {"orderId": "order1"}}
        self.handler.channel_config = {"test-sol": {"executor": "futures", "notional_usdt": "100"}}
        self.handler.workers.shutdown()
        self.handler.workers = MagicMock()

    def test_confirm_submits_once_and_places_sol_order(self):
        self.enable_sol()
        self.handler.handle(self.event("confirm"))
        self.handler.handle(self.event("confirm"))
        self.handler.workers.submit.assert_called_once()
        self.handler._execute("123")
        order = self.handler.bitget.place_futures_order.call_args.args[0]
        self.assertEqual((order.symbol, order.quantity, order.price), ("SOLUSDT", Decimal("1"), Decimal("100")))
        self.assertEqual((order.take_profit, order.stop_loss), (Decimal("105.5"), Decimal("94.5")))
        self.assertEqual(self.db.get_signal("123")["status"], "succeeded")

    def test_order_timeout_requires_manual_check(self):
        self.enable_sol()
        self.handler.bitget.place_futures_order.side_effect = TimeoutError("timeout")
        self.handler.handle(self.event("confirm"))
        with self.assertLogs(level="ERROR"):
            self.handler._execute("123")
        self.assertEqual(self.db.get_signal("123")["status"], "uncertain")

    def test_ignore_updates_database_and_removes_buttons(self):
        response = self.handler.handle(self.event("ignore"))
        self.assertEqual(self.db.get_signal("123")["status"], "ignored")
        self.assertFalse(any(e["tag"] == "action" for e in response.card.data["elements"]))
        self.handler.handle(self.event("ignore"))
        self.assertEqual(self.db.get_signal("123")["status"], "ignored")

    def test_other_user_is_rejected(self):
        response = self.handler.handle(self.event("ignore", "ou_other"))
        self.assertEqual(response.toast.type, "error")
        self.assertEqual(self.db.get_signal("123")["status"], "pending")
