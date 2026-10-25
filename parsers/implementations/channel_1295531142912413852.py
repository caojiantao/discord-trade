"""舒琴频道文字信号；模糊止损仅提取原文参考边界。"""

import re
from datetime import datetime
from decimal import Decimal

from ..base import SignalParser
from ..models import Direction, TradeSignal


class Channel1295531142912413852Parser(SignalParser):
    NUMBER = r"\d+(?:\.\d+)?"

    def parse(self, content: str, *, signal_time: datetime, source_id: str) -> TradeSignal | None:
        content = content.replace("\\n", "\n").replace("：", ":")
        # 旧导出把被回复的全文放在分隔线前；只读取后面的新正文。
        if content.lstrip().startswith("回复 @"):
            parts = re.split(r"(?m)^-{3,}\s*$", content, maxsplit=1)
            if len(parts) != 2:
                return None
            content = parts[1]
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        positions = [i for i, line in enumerate(lines) if line.startswith("方向:")]
        if len(positions) != 1 or positions[0] == 0:
            return None
        position = positions[0]
        symbol = lines[position - 1]
        if ":" in symbol or symbol.startswith((">", "回复")):
            return None
        fields = {}
        for line in lines[position:]:
            key, separator, value = line.partition(":")
            if separator and key in {"方向", "入场", "止盈", "止损"}:
                if key in fields:
                    return None
                fields[key] = value.strip()
        if set(fields) != {"方向", "入场", "止盈", "止损"}:
            return None
        long = bool(re.search(r"做多|多单", fields["方向"]))
        short = bool(re.search(r"做空|空单", fields["方向"]))
        if long == short:
            return None

        # 入场：8-8.08万附近 / 当前2740附近 / 8.05和8.2万附近分批入场
        n = self.NUMBER
        entry_text = re.sub(r"[，,]低倍或者现货$", "", fields["入场"])
        entry = re.fullmatch(
            rf"(?:当前价格|当前颈线|当前|现在|前高附近|前低|接近|临近)?\s*({n})\s*([万wW]?)"
            rf"(?:\s*[-—~～至和]\s*({n})\s*([万wW]?))?"
            rf"(?:附近)?(?:入场|建仓|做空|分批入场)?[。.]?", entry_text,
        )
        if entry is None:
            # 入场：当前2750附近建仓，2800附近补仓
            # 入场：174附近建仓，然后在180附近补空
            entry = re.fullmatch(
                rf"(?:当前|现在|临近)?({n})([万wW]?)(?:附近)?建仓[，,。]"
                rf"(?:然后在|接近)?({n})([万wW]?)(?:附近)?(?:补仓|补空)[。.]?", entry_text,
            )
        if entry is None:
            return None
        raw_entries = [(entry[1], entry[2])]
        if entry[3] is not None:
            raw_entries.append((entry[3], entry[4]))
        # 从价格字段中的明确单位推断省略单位，不根据品种名称猜测。
        # 整条信号都没写“万/W”时，保留原始数字。
        scale = Decimal(10000) if (
            re.search(rf"{n}\s*[万wW]", " ".join(fields[key] for key in ("入场", "止盈", "止损")))
        ) else Decimal(1)

        def price(value: str, unit: str) -> Decimal:
            amount = Decimal(value)
            if unit:
                return amount * Decimal(10000)
            # 已写成 71000 等完整报价时不再沿用“万”。
            return amount * (scale if amount < 100 else Decimal(1))

        entries = tuple(price(value, unit) for value, unit in raw_entries)
        # 止盈：点位1：8.23附近（求稳） 点位2：8.4附近 点位3：8.7万
        # 止盈：1：168附近（求稳） 点位2：158附近
        parts = re.split(r"(?:点位\s*\d*|(?<!\d)\d+)\s*:", fields["止盈"])[1:]
        targets = []
        for part in parts:
            target = re.match(rf"\s*(?:接近|前低|长线拿到)?({n})([万wW]?)", part)
            if target:
                if re.match(r"\s*[-—~～至和\d.]", part[target.end():]):
                    return None
                targets.append(price(target[1], target[2]))
        if not parts:
            target = re.fullmatch(rf"({n})([万wW]?)(?:附近)?", fields["止盈"])
            if target:
                targets.append(price(target[1], target[2]))
        # 止损：小幅跌破前低7.9止损。 / 小幅涨破8.5万一点。 / 2765
        # 不提取“拿3-4天”“2倍不会爆仓”里的数字。
        stop = re.match(
            rf"^(?:小幅(?:跌破|涨破)?(?:前低|前高|前)?|短线可以在突破颈线)({n})([万wW]?)",
            fields["止损"],
        )
        if stop is None:
            stop = re.fullmatch(rf"({n})([万wW]?)", fields["止损"])
        if not targets or stop is None:
            return None
        signal = TradeSignal(signal_time, symbol, entries,
                             Direction.LONG if long else Direction.SHORT,
                             tuple(targets), price(stop[1], stop[2]), source_id)
        self._validate(signal)
        return signal

