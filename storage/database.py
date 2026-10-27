"""原始 Discord 消息和交易信号的 SQLite 存储。"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from parsers.models import TradeSignal
from .models import DiscordMessage


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                -- Discord 原始消息；没有解析出信号的消息也保留，供溯源和展示回复关系。
                CREATE TABLE IF NOT EXISTS discord_messages (
                    message_id TEXT PRIMARY KEY,          -- Discord 消息 ID，文本存储避免大整数精度丢失
                    message_url TEXT NOT NULL UNIQUE,     -- 当前消息链接，作为溯源地址
                    channel_id TEXT NOT NULL,             -- 来源频道 ID，用于选择解析器和交易执行器
                    author_id TEXT NOT NULL,              -- 消息作者 ID
                    author_name TEXT NOT NULL,            -- 接收时的作者名称
                    content TEXT NOT NULL,                -- 消息正文，回复首行由监听层提取为 reply_to_url
                    embeds_json TEXT NOT NULL,            -- 嵌入内容 JSON 数组
                    attachments_json TEXT NOT NULL,       -- 图片等附件元数据 JSON 数组
                    reply_to_url TEXT,                    -- 被回复消息链接；允许原消息尚未收录
                    sent_at TEXT NOT NULL,                -- Discord 发送时间，带时区 ISO 8601 字符串
                    received_at TEXT NOT NULL             -- 本程序接收时间，UTC ISO 8601 字符串
                );
                -- 按原消息链接查找后续回复，供消息关联页面使用。
                CREATE INDEX IF NOT EXISTS idx_messages_reply
                    ON discord_messages(reply_to_url);
                -- 群转发记录；与个人交易确认卡片的消息 ID 独立。
                CREATE TABLE IF NOT EXISTS forwarded_messages (
                    message_id TEXT NOT NULL,           -- Discord 原消息 ID
                    message_url TEXT NOT NULL,          -- 按回复链接定位原消息
                    chat_id TEXT NOT NULL,              -- 飞书目标群 ID
                    feishu_message_id TEXT NOT NULL,    -- 飞书消息 ID，可用于回复
                    created_at TEXT NOT NULL,           -- 转发完成时间
                    PRIMARY KEY (message_url, chat_id)
                );
                -- 解析后的交易信号及确认状态；一条 Discord 消息最多生成一个信号。
                CREATE TABLE IF NOT EXISTS trade_signals (
                    -- 直接用原消息 ID 标识信号，关联关系由业务流程维护。
                    message_id TEXT NOT NULL PRIMARY KEY,
                    signal_json TEXT NOT NULL,            -- 完整 TradeSignal JSON，价格以字符串保存
                    -- 待确认、已忽略、执行中、执行失败、执行成功、结果待确认。
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'ignored', 'executing',
                                          'failed', 'succeeded', 'uncertain')),
                    feishu_message_id TEXT,               -- 飞书消息 ID，用于更新原确认卡片
                    result_json TEXT,                     -- 各笔订单执行结果或错误信息 JSON
                    created_at TEXT NOT NULL,             -- 信号入库时间，UTC ISO 8601 字符串
                    updated_at TEXT NOT NULL              -- 最近更新时间，UTC ISO 8601 字符串
                );
            """)

    @contextmanager
    def _connect(self):
        # 每次操作使用独立连接，事务结束后关闭，可供后续飞书回调线程使用。
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_message(self, message: DiscordMessage) -> bool:
        """重复投递不覆盖原消息；返回是否首次插入。"""
        with self._connect() as connection:
            cursor = connection.execute("""
                INSERT INTO discord_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO NOTHING
            """, (message.message_id, message.message_url, message.channel_id,
                  message.author_id, message.author_name, message.content,
                  json.dumps(message.embeds, ensure_ascii=False),
                  json.dumps(message.attachments, ensure_ascii=False), message.reply_to_url,
                  message.sent_at.isoformat(), message.received_at.isoformat()))
            return cursor.rowcount == 1

    def get_forwarded_message(self, message_url: str, chat_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT feishu_message_id FROM forwarded_messages WHERE message_url = ? AND chat_id = ?",
                (message_url, chat_id),
            ).fetchone()
            return row[0] if row else None

    def save_forwarded_message(self, message_id: str, message_url: str, chat_id: str, feishu_id: str):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO forwarded_messages VALUES (?, ?, ?, ?, ?)",
                (message_id, message_url, chat_id, feishu_id, self._now()),
            )

    def save_signal(self, message_id: str, signal: TradeSignal) -> str | None:
        """一条消息只创建一个待确认信号；重复解析返回 None。"""
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute("""
                INSERT INTO trade_signals(message_id, signal_json, created_at, updated_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(message_id) DO NOTHING
            """, (str(message_id), json.dumps(asdict(signal), ensure_ascii=False, default=str), now, now))
            return str(message_id) if cursor.rowcount else None

    def get_signal(self, message_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("""
                SELECT s.*, m.channel_id FROM trade_signals s
                LEFT JOIN discord_messages m ON m.message_id = s.message_id WHERE s.message_id = ?
            """, (str(message_id),)).fetchone()
            return dict(row) if row else None

    def get_replies(self, message_url: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT * FROM discord_messages WHERE reply_to_url = ? ORDER BY sent_at
            """, (message_url,)).fetchall()
            return [dict(row) for row in rows]

    def transition(self, message_id: str, expected: str, target: str, *, result=None) -> bool:
        allowed = {
            "pending": {"ignored", "executing"},
            "executing": {"failed", "succeeded", "uncertain"},
        }
        if target not in allowed.get(expected, set()):
            raise ValueError(f"不支持的信号状态流转：{expected} -> {target}")
        # 状态条件与更新放在同一 SQL 中，只有首次确认才能取得执行权。
        with self._connect() as connection:
            cursor = connection.execute("""
                UPDATE trade_signals SET status = ?, result_json = ?, updated_at = ?
                WHERE message_id = ? AND status = ?
            """, (target, json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                  self._now(), str(message_id), expected))
            return cursor.rowcount == 1

    def set_feishu_message_id(self, message_id: str, feishu_message_id: str):
        with self._connect() as connection:
            connection.execute("""
                UPDATE trade_signals SET feishu_message_id = ?, updated_at = ? WHERE message_id = ?
            """, (feishu_message_id, self._now(), str(message_id)))

    def recover_executing(self) -> int:
        # 重启时遗留执行中的订单可能已送达交易所，标为待核实，禁止自动重试。
        with self._connect() as connection:
            return connection.execute("""
                UPDATE trade_signals SET status = 'uncertain', updated_at = ?
                WHERE status = 'executing'
            """, (self._now(),)).rowcount
