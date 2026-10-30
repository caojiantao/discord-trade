import tempfile
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from notifications.forwarding import forward_message, format_message, image_urls
from notifications.feishu import FeishuNotifier
from storage.database import Database
from storage.models import DiscordMessage


class ForwardingTest(unittest.TestCase):
    def test_role_mentions_removed_from_forwarded_text(self):
        message = DiscordMessage("1", "url", "2", "3", "作者",
                                 "开仓 <@&1553355670802403358>\n<@&123>注意风险",
                                 [], [], None, datetime.now(timezone.utc))
        self.assertEqual(format_message(message), "开仓 \n注意风险")
        self.assertIn("<@&1553355670802403358>", message.content)

    def test_translation_ignored_and_embed_images_detected(self):
        message = DiscordMessage("1", "url", "2", "3", "Josh", "original text",
                                 [{"description": "翻译内容", "image": {"url": "https://example.com/chart.png"}},
                                  {"thumbnail": {"url": "https://example.com/chart.png"}}],
                                 [{"url": "https://example.com/photo.jpg?ex=123"}],
                                 None, datetime.now(timezone.utc))
        self.assertEqual(format_message(message), "original text")
        self.assertEqual(image_urls(message), ["https://example.com/photo.jpg?ex=123",
                                              "https://example.com/chart.png"])

    def test_shuqin_text_and_image_in_one_message(self):
        """真实消息 fixture；模拟下载及飞书 SDK，验证完整转发和入库。"""
        data = json.loads((Path(__file__).parent / "fixtures/shuqin_image_message.json").read_text())
        data["sent_at"] = datetime.fromisoformat(data["sent_at"])
        message = DiscordMessage(**data)
        image_url = message.attachments[0]["url"]
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            with patch("notifications.feishu.build_opener") as build_opener:
                notifier = FeishuNotifier("test-app", "test-secret", proxy="http://127.0.0.1:7890")
                self.assertEqual(build_opener.call_args.args[0].proxies,
                                 {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})
                download = MagicMock()
                download.__enter__.return_value.read.return_value = b"test-image-bytes"
                build_opener.return_value.open.return_value = download
                notifier._client = Mock()
                upload = notifier._client.im.v1.image.create.return_value
                upload.success.return_value = True
                upload.data.image_key = "img_test_shuqin"
                sent = notifier._client.im.v1.message.create.return_value
                sent.success.return_value = True
                sent.data.message_id = "om_shuqin"

                forward_message(message, "oc_group", notifier, db)

                self.assertEqual(build_opener.return_value.open.call_args.args[0].full_url, image_url)
                upload_body = notifier._client.im.v1.image.create.call_args.args[0].request_body
                self.assertEqual(upload_body.image.read(), b"test-image-bytes")
                self.assertEqual(upload_body.image_type, "message")
                notifier._client.im.v1.message.create.assert_called_once()
                body = notifier._client.im.v1.message.create.call_args.args[0].request_body
                self.assertEqual(body.msg_type, "post")
                self.assertEqual(json.loads(body.content), {"zh_cn": {"content": [
                    [{"tag": "text", "text": message.content.replace("<@&1553355683657683008>", "")}],
                    [{"tag": "img", "image_key": "img_test_shuqin"}],
                ]}})
                self.assertEqual(db.get_forwarded_message(message.message_url, "oc_group"), "om_shuqin")

    def test_empty_proxy_disables_environment_proxy(self):
        with patch("notifications.feishu.build_opener") as build_opener:
            FeishuNotifier("test-app", "test-secret", proxy=None)
            self.assertEqual(build_opener.call_args.args[0].proxies, {})

    def test_reply_mapping_and_missing_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            notifier = Mock()
            notifier.send_post.side_effect = ["om_root", "om_fallback"]
            notifier.reply_post.return_value = "om_reply"

            def message(mid, reply=None):
                return DiscordMessage(mid, f"https://discord.com/channels/1/2/{mid}",
                                      "2", "3", "作者", "正文", [], [], reply,
                                      datetime.now(timezone.utc))

            root = message("1")
            forward_message(root, "oc_group", notifier, db)
            forward_message(root, "oc_group", notifier, db)
            self.assertEqual(notifier.send_post.call_count, 1)
            reply = message("2", root.message_url)
            forward_message(reply, "oc_group", notifier, db)
            self.assertEqual(notifier.reply_post.call_args.args[0], "om_root")
            self.assertEqual(db.get_forwarded_message(reply.message_url, "oc_group"), "om_reply")
            self.assertIsNone(db.get_forwarded_message(root.message_url, "oc_other"))
            forward_message(message("3", "missing"), "oc_group", notifier, db)
            self.assertEqual(notifier.send_post.call_count, 2)
