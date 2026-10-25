import os
import unittest
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import app, credentials

from notifications.feishu import FeishuNotifier
from notifications.confirmation import build_signal_card
from parsers.implementations.channel_1488133240975003761 import Channel1488133240975003761Parser
from parsers.implementations.channel_1464406516282167448 import Channel1464406516282167448Parser
from storage.database import Database
from storage.models import DiscordMessage


@unittest.skipUnless(
    os.environ.get("RUN_FEISHU_INTEGRATION") == "1",
    "设置 RUN_FEISHU_INTEGRATION=1 才发送真实飞书测试消息",
)
class FeishuIntegrationTest(unittest.TestCase):
    """飞书真实发送测试；默认跳过，避免普通单测产生外部消息。"""

    def test_send_text(self):
        self.assertTrue(credentials.FEISHU_APP_ID)
        self.assertTrue(credentials.FEISHU_APP_SECRET)
        self.assertTrue(credentials.FEISHU_RECEIVE_ID)
        FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET).send_text(
            credentials.FEISHU_RECEIVE_ID,
            "测试消息：Discord 信号通知已接通。",
            receive_id_type=credentials.FEISHU_RECEIVE_ID_TYPE,
        )

    def test_send_confirmation_card(self):
        """写入模拟消息和信号，发送真实卡片；由 listener.py 接收点击回调。"""
        database = Database(Path(__file__).resolve().parents[1] / app.DATABASE_PATH)
        # 每次使用新标识，可重复测试；明确标记模拟来源，不伪造真实 Discord 链接。
        message_id = f"test-{uuid4().hex}"
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        content = "GOLD BUY NOW\n@ 4538\n\nTP : 4550\nTP : 4570\n\nSL : 4522"
        source = f"urn:discord-trade:test:{message_id}"
        database.save_message(DiscordMessage(
            message_id=message_id, message_url=source,
            channel_id="1488133240975003761", author_id="test", author_name="模拟信号",
            content=content, embeds=[], attachments=[], reply_to_url=None, sent_at=now,
        ))
        signal = Channel1488133240975003761Parser().parse(
            content, signal_time=now, source_id=source,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(database.save_signal(message_id, signal), message_id)
        row = database.get_signal(message_id)
        card = build_signal_card(message_id, json.loads(row["signal_json"]))
        card["header"]["title"]["content"] = "模拟信号 · 卡片交互测试（不下单）"
        feishu_message_id = FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET).send_card(
            credentials.FEISHU_RECEIVE_ID, card,
        )
        self.assertTrue(feishu_message_id)
        database.set_feishu_message_id(message_id, feishu_message_id)
        logging.warning("test_card_sent message_id=%s feishu_message_id=%s", message_id, feishu_message_id)

    def test_send_sol_live_order_card(self):
        """发送真实挂单确认卡片；只有点击确认后才由监听程序提交 Bitget。"""
        database = Database(Path(__file__).resolve().parents[1] / app.DATABASE_PATH)
        message_id = f"live-sol-{uuid4().hex}"
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        content = "Sol做多策略：100做多，止损94.5，目标一105.5，目标二待定。仅纪录个人观点和操作，不构成交易建议。"
        source = "https://discord.com/channels/1295108691275813036/1464406516282167448/1561053322620829881"
        database.save_message(DiscordMessage(
            message_id=message_id, message_url=f"urn:discord-trade:live-sol:{message_id}",
            channel_id="test-sol", author_id="test", author_name="SOL 实盘交互测试",
            content=content, embeds=[], attachments=[], reply_to_url=None, sent_at=now,
        ))
        signal = Channel1464406516282167448Parser().parse(content, signal_time=now, source_id=source)
        self.assertIsNotNone(signal)
        database.save_signal(message_id, signal)
        row = database.get_signal(message_id)
        card = build_signal_card(message_id, json.loads(row["signal_json"]))
        card["header"]["title"]["content"] = "SOL 实盘限价挂单 · 待确认"
        card["elements"].insert(0, {"tag": "div", "text": {"tag": "plain_text",
            "content": "确认后真实下单：SOLUSDT，100 USDT 名义仓位，数量 1 SOL，限价 100；TP 105.5，SL 94.5。"}})
        feishu_message_id = FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET).send_card(
            credentials.FEISHU_RECEIVE_ID, card)
        database.set_feishu_message_id(message_id, feishu_message_id)
        logging.warning("live_sol_card_sent message_id=%s feishu_message_id=%s", message_id, feishu_message_id)


if __name__ == "__main__":
    unittest.main()
