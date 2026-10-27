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
from notifications.forwarding import forward_message
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

    def test_send_message_with_image(self):
        """用线上记录构造消息，真实下载图片并转发；不解析信号、不下单。"""
        import tempfile
        from config.notifications import CHANNEL_FEISHU_CHATS

        message = DiscordMessage(
            message_id="1564458808993124434",
            message_url="https://discord.com/channels/1295108691275813036/1488133240975003761/1564458808993124434",
            channel_id="1488133240975003761", author_id="1488134266620743710",
            author_name="PREMIUM SIGNALS",
            content="This setup looked bit weak but this is market anything happen \n\nIf u still in manage your trade reduce the risk or go with B.E",
            embeds=[{"flags": 0, "color": 3108845, "type": "rich",
                     "description": "这个开局看起来有点弱，但这就是市场，什么事都有可能发生。\n\n如果你仍然想继续交易，请降低风险或选择盈亏平衡点。"}],
            attachments=[{
                "filename": "--36603691008.jpg", "flags": 0, "id": 1564458808783282306,
                "proxy_url": "https://media.discordapp.net/attachments/1488133240975003761/1564458808783282306/--36603691008.jpg?ex=6ae1574e&is=6ae005ce&hm=31ea70274812ea9713f6b8595f9f866d8ca1bca910fbacc98897d9e0ce7a5e7c&",
                "url": "https://cdn.discordapp.com/attachments/1488133240975003761/1564458808783282306/--36603691008.jpg?ex=6ae1574e&is=6ae005ce&hm=31ea70274812ea9713f6b8595f9f866d8ca1bca910fbacc98897d9e0ce7a5e7c&",
                "size": 112591, "height": 2390, "width": 1320, "content_type": "image/jpeg",
            }],
            reply_to_url="https://discord.com/channels/1295108691275813036/1488133240975003761/1564348581488623707",
            sent_at=datetime.fromisoformat("2026-10-27T02:00:46.303000+00:00"),
            received_at=datetime.fromisoformat("2026-10-27T02:00:46.635808+00:00"),
        )
        chat_id = CHANNEL_FEISHU_CHATS.get(int(message.channel_id))
        self.assertTrue(chat_id, "请先配置黄金频道对应的 CHANNEL_FEISHU_CHATS")
        notifier = FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET,
                                  proxy=app.HTTP_PROXY)
        # 使用临时映射表，方便重复发送，不改变生产转发记录。
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "forwarding.sqlite3")
            forward_message(message, chat_id, notifier, database)
            self.assertTrue(database.get_forwarded_message(message.message_url, chat_id))

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

    def test_send_cfd_live_order_card(self):
        """发送黄金做空确认卡片，点击确认后按实际行情提交两笔 CFD 订单。"""
        database = Database(Path(__file__).resolve().parents[1] / app.DATABASE_PATH)
        message_id = f"live-cfd-{uuid4().hex}"
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        content = "GOLD SELL NOW\n@ 4772\nMORE SELL @ 4780\n\nTP : 4757\nTP : 4742\n\nSL : 4786"
        source = f"urn:discord-trade:live-cfd:{message_id}"
        # 使用黄金频道配置，与实际消息共用解析器、行情查询和执行器。
        database.save_message(DiscordMessage(
            message_id=message_id, message_url=source,
            channel_id="1488133240975003761", author_id="test", author_name="CFD 实盘交互测试",
            content=content, embeds=[], attachments=[], reply_to_url=None, sent_at=now,
        ))
        signal = Channel1488133240975003761Parser().parse(
            content, signal_time=now, source_id=source,
        )
        self.assertIsNotNone(signal)
        database.save_signal(message_id, signal)
        row = database.get_signal(message_id)
        card = build_signal_card(message_id, json.loads(row["signal_json"]))
        card["header"]["title"]["content"] = "黄金 CFD 实盘做空 · 待确认"
        from config import trading
        settings = trading.CHANNEL_TRADING_CONFIG[1488133240975003761]
        card["elements"].insert(0, {"tag": "div", "text": {"tag": "plain_text",
            "content": f"确认后真实下单：XAUUSD.s，做空两笔，每笔 {settings['lots']} 手；"
                       f"入场 4772 / 4780，TP 4757，SL 4786。"
                       f"按确认时行情判断市价或限价，阈值 {settings['threshold']}。"}})
        feishu_message_id = FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET).send_card(
            credentials.FEISHU_RECEIVE_ID, card)
        self.assertTrue(feishu_message_id)
        database.set_feishu_message_id(message_id, feishu_message_id)
        logging.warning("live_cfd_card_sent message_id=%s feishu_message_id=%s", message_id, feishu_message_id)


if __name__ == "__main__":
    unittest.main()
