"""消息入库实体。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class DiscordMessage:
    message_id: str
    message_url: str
    channel_id: str
    author_id: str
    author_name: str
    content: str
    embeds: list[dict]
    attachments: list[dict]
    reply_to_url: str | None
    sent_at: datetime
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
