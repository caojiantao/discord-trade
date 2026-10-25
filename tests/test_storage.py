import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from parsers.models import Direction, TradeSignal
from storage.database import Database
from storage.models import DiscordMessage


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.db = Database(self.path)
        self.time = datetime.now(timezone.utc)

    def save_message(self, message_id="1", reply_to_url=None):
        return self.db.save_message(DiscordMessage(
            message_id=message_id, message_url=f"https://discord.com/channels/1/2/{message_id}",
            channel_id="2", author_id="3", author_name="作者", content="原始正文\n下一行",
            embeds=[{"description": "嵌入正文"}], attachments=[{"url": "https://example.com/a.jpg"}],
            reply_to_url=reply_to_url, sent_at=self.time,
        ))

    def save_signal(self):
        self.save_message()
        signal = TradeSignal(self.time, "GOLD", (Decimal("4538"),), Direction.LONG,
                             (Decimal("4550"), Decimal("4570")), Decimal("4522"),
                             "https://discord.com/channels/1/2/1")
        return self.db.save_signal("1", signal), signal

    def test_original_messages_and_reply_without_parent(self):
        url = "https://discord.com/channels/1/2/999"
        self.assertTrue(self.save_message(reply_to_url=url))
        self.assertFalse(self.save_message(reply_to_url=url))
        replies = self.db.get_replies(url)
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["content"], "原始正文\n下一行")
        self.assertEqual(json.loads(replies[0]["embeds_json"])[0]["description"], "嵌入正文")

    def test_signal_persistence_and_deduplication(self):
        signal_id, signal = self.save_signal()
        self.assertEqual(signal_id, "1")
        self.assertIsNone(self.db.save_signal("1", signal))
        row = Database(self.path).get_signal(signal_id)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["channel_id"], "2")
        data = json.loads(row["signal_json"])
        self.assertEqual(data["entry_prices"], ["4538"])
        self.assertEqual(data["direction"], "long")

    def test_confirm_once_and_recover_after_restart(self):
        signal_id, _ = self.save_signal()
        self.assertTrue(self.db.transition(signal_id, "pending", "executing"))
        self.assertFalse(self.db.transition(signal_id, "pending", "executing"))
        restarted = Database(self.path)
        self.assertEqual(restarted.recover_executing(), 1)
        self.assertEqual(restarted.get_signal(signal_id)["status"], "uncertain")
        self.assertFalse(restarted.transition(signal_id, "pending", "executing"))

    def test_result_and_terminal_status(self):
        signal_id, _ = self.save_signal()
        self.db.set_feishu_message_id(signal_id, "om_test")
        self.db.transition(signal_id, "pending", "executing")
        self.assertTrue(self.db.transition(signal_id, "executing", "succeeded", result={"orderId": "123"}))
        row = self.db.get_signal(signal_id)
        self.assertEqual(row["feishu_message_id"], "om_test")
        self.assertEqual(json.loads(row["result_json"]), {"orderId": "123"})
        with self.assertRaises(ValueError):
            self.db.transition(signal_id, "succeeded", "executing")
