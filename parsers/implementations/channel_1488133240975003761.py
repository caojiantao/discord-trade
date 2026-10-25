"""PREMIUM SIGNALS 频道：解析黄金及外汇的完整文字开仓消息。"""

import re
from datetime import datetime
from decimal import Decimal

from ..base import SignalParser
from ..models import Direction, TradeSignal


class Channel1488133240975003761Parser(SignalParser):
    def parse(self, content: str, *, signal_time: datetime, source_id: str) -> TradeSignal | None:
        # CSV 使用字面量 \n 保存换行，Discord 则直接传入真实换行。
        lines = [line.strip().upper() for line in content.replace("\\n", "\n").splitlines()
                 if line.strip()]
        if not lines:
            return None
        # 从首行严格匹配新开仓，避免把“回复: [旧信号]”里的内容当成新信号。
        header = re.fullmatch(r"(\S+)\s+(BUY|SELL)\s+(NOW|LIMIT)", lines[0])
        if header is None:
            return None

        number = r"\d+(?:\.\d+)?"
        entries: list[Decimal] = []
        targets: list[Decimal] = []
        stop = None
        for line in lines[1:]:
            # @ 4792
            # @ 4378 - 4368
            entry = re.fullmatch(rf"@\s*({number})(?:\s*-\s*({number}))?", line)
            # MORE BUY @ 4782
            # MORE SELL @ 4320
            more = re.fullmatch(rf"MORE\s+(BUY|SELL)\s*@\s*({number})", line)
            # TP : 4810
            # TP : OPEN
            # TP : LATER
            target = re.fullmatch(rf"TP\s*:\s*({number}|OPEN|LATER)", line)
            # SL : 4770
            loss = re.fullmatch(rf"SL\s*:\s*({number})", line)
            if entry and not entries:
                entries.append(Decimal(entry[1]))
                # 区间第二个价格等同于 MORE，按原顺序加入入场列表。
                if entry[2] is not None:
                    entries.append(Decimal(entry[2]))
            elif more and entries:
                entries.append(Decimal(more[2]))
            elif target:
                # 开放目标没有明确价格，不凭空补值；至少需要一个数字止盈。
                if target[1] not in {"OPEN", "LATER"}:
                    targets.append(Decimal(target[1]))
            elif loss and stop is None:
                stop = Decimal(loss[1])
            else:
                return None
        if not entries or not targets or stop is None:
            return None

        signal = TradeSignal(
            signal_time=signal_time,
            # 品种沿用消息中的名称，解析层不做交易平台的品种映射。
            symbol=header[1],
            entry_prices=tuple(entries),
            direction=Direction.LONG if header[2] == "BUY" else Direction.SHORT,
            take_profits=tuple(targets), stop_loss=stop, source_id=source_id,
        )
        self._validate(signal, reverse_long_entries=True)
        return signal

