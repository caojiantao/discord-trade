"""日内交易频道的文字开仓信号。"""

import re
from datetime import datetime
from decimal import Decimal

from ..base import SignalParser
from ..models import Direction, TradeSignal


class Channel1386949813743915029Parser(SignalParser):
    NUMBER = r"\d+(?:\.\d+)?"

    def parse(self, content: str, *, signal_time: datetime, source_id: str) -> TradeSignal | None:
        content = content.replace("\\n", "\n").replace("：", ":")
        if content.lstrip().startswith("回复 @"):
            parts = re.split(r"(?m)^-{3,}\s*$", content, maxsplit=1)
            if len(parts) != 2:
                return None
            content = parts[1]
        # 引用摘要不是新正文；回复下方仍可能包含新的完整信号。
        lines = [re.sub(r"@everyone|<@[^>]+>", "", line).strip()
                 for line in content.splitlines() if not line.lstrip().startswith(">")]
        lines = [line for line in lines if line]
        n = self.NUMBER
        headers = []
        for i, line in enumerate(lines):
            # BTC 多 / Btc做多 / Eth周末小仓空 / BTC 小仓试空
            header = re.fullmatch(r"([A-Za-z]+|比特币)([^\d\n]*)", line)
            if header and bool("多" in header[2]) != bool("空" in header[2]):
                headers.append((i, header))
        if len(headers) != 1:
            return None
        position, header = headers[0]
        entries, targets, stops = [], [], []
        for line in lines[position + 1:]:
            # SL：80200 / sl 2435
            stop = re.fullmatch(rf"SL\s*:?\s*({n})", line, re.I)
            if stop:
                stops.append(Decimal(stop[1]))
                continue
            # TP1：83500 / Tp2 2535 / TP：70600
            target = re.fullmatch(rf"TP(?:\d+)?\s*:?\s*({n})", line, re.I)
            if target:
                targets.append(Decimal(target[1]))
                continue
            # 81700-82100 / 现价0.505-0.51 / 现价80900附近第一注
            # 79700补仓第二注 / 补仓109200 / 109700附近
            entry = re.fullmatch(
                rf"(?:现价|补仓[: ]?)?\s*({n})(?:\s*[-—~～]\s*({n}))?"
                r"(?:附近|左右|现价)?(?:多|空|第一[注单仓]|第二[注单仓]|补仓(?:第二[注单仓])?)?", line,
            )
            if entry:
                entries.append(Decimal(entry[1]))
                if entry[2] is not None:
                    entries.append(Decimal(entry[2]))
                continue
            # 现价进一单 / 78500 上下200点左右：缺少明确价格或边界，整条忽略。
            if re.search(r"现价|补仓|第一[注单仓]|第二[注单仓]|上下", line) or re.match(rf"{n}", line):
                return None
            if re.match(r"(?:SL|TP)\b|TP\d|TPP", line, re.I):
                return None
        if not entries or not targets or len(stops) != 1:
            return None
        signal = TradeSignal(signal_time, header[1], tuple(entries),
                             Direction.LONG if "多" in header[2] else Direction.SHORT,
                             tuple(targets), stops[0], source_id)
        # 保留原文价格顺序；顺序不符合基类规则时交由异常日志记录来源。
        self._validate(signal)
        return signal
