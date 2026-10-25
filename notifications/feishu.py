"""飞书机器人通知的最小封装。"""

import json

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody


class FeishuNotifier:
    """使用企业应用凭据向飞书用户或群聊发送文本。"""

    def __init__(self, app_id: str, app_secret: str):
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    def send_text(self, receive_id: str, text: str, *, receive_id_type: str = "chat_id") -> str:
        """发送文本；receive_id 默认是群聊 chat_id，也可以是 open_id。"""
        return self._send(receive_id, "text", {"text": text}, receive_id_type)

    def send_card(self, receive_id: str, card: dict) -> str:
        """向个人发送交互卡片，返回消息 ID 供后续更新。"""
        return self._send(receive_id, "interactive", card, "open_id")

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
