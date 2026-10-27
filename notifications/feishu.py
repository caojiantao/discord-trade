"""飞书机器人通知的最小封装。"""

import json
from io import BytesIO
from urllib.request import Request, build_opener, ProxyHandler

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody


class FeishuNotifier:
    """使用企业应用凭据向飞书用户或群聊发送文本。"""

    def __init__(self, app_id: str, app_secret: str, proxy: str | None = None):
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        # Discord 图片地址可能无法直连，下载图片时沿用程序代理配置。
        self._url_opener = build_opener(ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))

    def send_text(self, receive_id: str, text: str, *, receive_id_type: str = "chat_id") -> str:
        """发送文本；receive_id 默认是群聊 chat_id，也可以是 open_id。"""
        return self._send(receive_id, "text", {"text": text}, receive_id_type)

    def upload_image_url(self, url: str) -> str:
        """下载 Discord 图片并上传到飞书，返回 image_key。"""
        with self._url_opener.open(Request(url, headers={"User-Agent": "discord-trade/1.0"}), timeout=15) as response:
            data = response.read()
        request = (CreateImageRequest.builder()
                   .request_body(CreateImageRequestBody.builder()
                                 .image(BytesIO(data)).image_type("message").build()).build())
        response = self._client.im.v1.image.create(request)
        if not response.success():
            raise RuntimeError(f"飞书图片上传失败：code={response.code}, msg={response.msg}")
        return response.data.image_key

    def send_post(self, receive_id: str, content: dict, *, receive_id_type: str = "chat_id") -> str:
        return self._send(receive_id, "post", content, receive_id_type)

    def reply_post(self, message_id: str, content: dict) -> str:
        request = (ReplyMessageRequest.builder().message_id(message_id)
                   .request_body(ReplyMessageRequestBody.builder().msg_type("post")
                                 .content(json.dumps(content, ensure_ascii=False))
                                 .reply_in_thread(False).build()).build())
        response = self._client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(f"飞书回复失败：code={response.code}, msg={response.msg}")
        return response.data.message_id

    def send_card(self, receive_id: str, card: dict) -> str:
        """向个人发送交互卡片，返回消息 ID 供后续更新。"""
        return self._send(receive_id, "interactive", card, "open_id")

    def reply_text(self, message_id: str, text: str) -> str:
        """回复已转发的消息，返回当前回复的消息 ID。"""
        request = (ReplyMessageRequest.builder().message_id(message_id)
                   .request_body(ReplyMessageRequestBody.builder().msg_type("text")
                                 .content(json.dumps({"text": text}, ensure_ascii=False))
                                 .reply_in_thread(False).build()).build())
        response = self._client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(f"飞书回复失败：code={response.code}, msg={response.msg}")
        return response.data.message_id

    def update_card(self, message_id: str, card: dict):
        request = (PatchMessageRequest.builder().message_id(message_id)
                   .request_body(PatchMessageRequestBody.builder()
                                 .content(json.dumps(card, ensure_ascii=False)).build()).build())
        response = self._client.im.v1.message.patch(request)
        if not response.success():
            raise RuntimeError(f"飞书更新失败：code={response.code}, msg={response.msg}")

    def _send(self, receive_id: str, msg_type: str, content: dict, receive_id_type: str) -> str:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type(msg_type)
                .content(json.dumps(content, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"飞书发送失败：code={response.code}, msg={response.msg}, "
                f"receive_id_type={receive_id_type}, receive_id={receive_id}"
            )
        return response.data.message_id
