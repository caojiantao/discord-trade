import asyncio
import json
import logging
import re
from dataclasses import asdict
from zoneinfo import ZoneInfo
from pathlib import Path
from multiprocessing import Process

import discord

from parsers.base import SignalParser
from parsers.implementations.channel_1295531142912413852 import Channel1295531142912413852Parser
from parsers.implementations.channel_1488133240975003761 import Channel1488133240975003761Parser
from parsers.implementations.channel_1386949813743915029 import Channel1386949813743915029Parser
from parsers.implementations.channel_1464406516282167448 import Channel1464406516282167448Parser
from config import app, credentials
from logging_setup import configure_logging
from notifications.feishu import FeishuNotifier
from notifications.forwarding import forward_message
from config.notifications import CHANNEL_FEISHU_CHATS
from notifications.confirmation import build_signal_card, run_confirmation_listener
from storage.database import Database
from storage.models import DiscordMessage

# 凭据和运行参数直接从各自配置模块读取。
TOKEN = credentials.DISCORD_TOKEN
PROXY = app.HTTP_PROXY or None

# 一个频道 ID 对应一个解析器；可继续添加频道。
CHANNEL_PARSERS: dict[int, SignalParser] = {
    1464406516282167448: Channel1464406516282167448Parser(),
    1386949813743915029: Channel1386949813743915029Parser(),
    1488133240975003761: Channel1488133240975003761Parser(),
    1295531142912413852: Channel1295531142912413852Parser(),
}

client = discord.Client(proxy=PROXY)
feishu = FeishuNotifier(credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET)
database = Database(Path(__file__).parent / app.DATABASE_PATH)


@client.event
async def on_ready():
    # 注册连接就绪事件；登录完成或部分重连场景下会触发。
    logging.info("已登录：%s，正在监听频道 %s", client.user, list(CHANNEL_PARSERS))


@client.event
async def on_message(message):

    # 首行包含同频道的 Discord 消息 Markdown 链接，才视为回复。
    first_line, _, remaining_content = message.content.partition("\n")
    reply_match = re.search(
        rf"\[[^\]\r\n]*\]\((https?://discord\.com/channels/\d+/{message.channel.id}/\d+)\)",
        first_line,
    )
    reply_message_link = reply_match.group(1) if reply_match else None
    # 移除回复首行后清掉开头的空行，保留正文内部的换行格式。
    content = remaining_content.lstrip("\r\n") if reply_match else message.content
    # 所有收到的消息先入库；回复链接单独保存，不依赖是否注册了解析器。
    stored_message = DiscordMessage(
        message_id=str(message.id), message_url=message.jump_url,
        channel_id=str(message.channel.id), author_id=str(message.author.id),
        author_name=str(message.author), content=content,
        embeds=[embed.to_dict() for embed in message.embeds],
        attachments=[attachment.to_dict() for attachment in message.attachments],
        reply_to_url=reply_message_link, sent_at=message.created_at,
    )
    logging.info("discord_message_save message=%s", stored_message)
    database.save_message(stored_message)

    # 配置了群机器人就转发所有消息；转发失败不影响后续信号解析。
    channel = CHANNEL_FEISHU_CHATS.get(message.channel.id, {})
    chat_id = channel.get("chat_id")
    if chat_id:
        try:
            await asyncio.to_thread(forward_message, stored_message, chat_id, feishu, database)
        except Exception:
            logging.exception("feishu_forward_failed channel_id=%s message_id=%s", message.channel.id, message.id)



    # 所有消息都入库，只有已注册频道的完整信号才发送确认卡片。
    parser = CHANNEL_PARSERS.get(message.channel.id)
    if parser is None:
        return
    try:
        signal = parser.parse(
            content,
            signal_time=message.created_at.astimezone(ZoneInfo("Asia/Shanghai")),
            source_id=message.jump_url,
        )
        if signal is None:
            return
        message_id = database.save_signal(str(message.id), signal)
        if message_id is None:
            return
        card = build_signal_card(message_id, json.loads(json.dumps(asdict(signal), default=str)),
                                 channel_id=message.channel.id)
        feishu_message_id = await asyncio.to_thread(feishu.send_card, credentials.FEISHU_RECEIVE_ID, card)
        database.set_feishu_message_id(message_id, feishu_message_id)
    except Exception:
        logging.exception("signal_notification_failed message_id=%s url=%s", message.id, message.jump_url)


if __name__ == "__main__":
    configure_logging(app)
    if not TOKEN:
        raise SystemExit("请先在 config/credentials.py 中填写 DISCORD_TOKEN。")
    # 只在主程序启动时恢复状态，子进程导入模块不应修改执行中的信号。
    database.recover_executing()
    # 长连接回调与 Discord 同时运行，共享 SQLite 中的信号状态。
    callback_process = Process(target=run_confirmation_listener, args=(
        credentials.FEISHU_APP_ID, credentials.FEISHU_APP_SECRET,
        str(Path(__file__).parent / app.DATABASE_PATH), credentials.FEISHU_RECEIVE_ID,
    ), daemon=True)
    callback_process.start()
    try:
        client.run(TOKEN)
    finally:
        callback_process.terminate()
        callback_process.join()
