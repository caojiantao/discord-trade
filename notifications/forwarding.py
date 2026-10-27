"""Discord 消息转发及飞书回复关联。"""

import logging
from urllib.parse import urlsplit

from storage.models import DiscordMessage


def is_image(attachment: dict) -> bool:
    # 部分附件没有 content_type，使用文件扩展名补充识别。
    return attachment.get("content_type", "").startswith("image/") or urlsplit(
        attachment.get("filename") or attachment.get("url", "")
    ).path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))


def image_urls(message: DiscordMessage) -> list[str]:
    urls = [item["url"] for item in message.attachments if item.get("url") and is_image(item)]
    for embed in message.embeds:
        for key in ("image", "thumbnail"):
            if embed.get(key, {}).get("url"):
                urls.append(embed[key]["url"])
    return list(dict.fromkeys(urls))


def format_message(message: DiscordMessage) -> str:
    # 转发正文保持 Discord 原样，不额外拼接作者、时间或原消息链接。
    lines = [message.content]
    # description 常用于频道的翻译内容，不转发；原始数据仍保留在数据库。
    for embed in message.embeds:
        lines.extend(str(embed[key]) for key in ("title", "url") if embed.get(key))
        for field in embed.get("fields", []):
            lines.append(f"{field.get('name', '')}: {field.get('value', '')}")
        for key in ("video",):
            if embed.get(key, {}).get("url"):
                lines.append(embed[key]["url"])
    lines.extend(item["url"] for item in message.attachments
                 if item.get("url") and not is_image(item))
    return "\n".join(lines)


def forward_message(message, chat_id, notifier, database):
    # 同一消息在同一群只转发一次；不同群的关联独立保存。
    if database.get_forwarded_message(message.message_url, chat_id):
        return
    parent_id = (database.get_forwarded_message(message.reply_to_url, chat_id)
                 if message.reply_to_url else None)
    text = format_message(message)
    urls = image_urls(message)
    logging.info("feishu_forward_start message_id=%s attachment_count=%s image_count=%s",
                 message.message_id, len(message.attachments), len(urls))
    image_keys = [notifier.upload_image_url(url) for url in urls]
    # post 富文本把正文和图片放在同一条飞书消息中。
    content = {"zh_cn": {"content": [[{"tag": "text", "text": text}]]}}
    for image_key in image_keys:
        content["zh_cn"]["content"].append([{"tag": "img", "image_key": image_key}])
    if parent_id:
        feishu_id = notifier.reply_post(parent_id, content)
    else:
        feishu_id = notifier.send_post(chat_id, content)
    database.save_forwarded_message(message.message_id, message.message_url, chat_id, feishu_id)
    logging.info("feishu_forward_success channel_id=%s message_id=%s feishu_message_id=%s",
                 message.channel_id, message.message_id, feishu_id)
