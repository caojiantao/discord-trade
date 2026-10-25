"""相会员群：解析正文中的完整文字策略。"""

import re
from datetime import datetime
from decimal import Decimal

from ..base import SignalParser
from ..models import Direction, TradeSignal


class Channel1464406516282167448Parser(SignalParser):
    NUMBER = r"\d+(?:\.\d+)?"

    def parse(self, content: str, *, signal_time: datetime, source_id: str) -> TradeSignal | None:
        content = content.replace("\\n", "\n").replace("：", ":")
        # 导出中的 > 行是引用原文；只解析本次发送的新正文。
        if content.lstrip().startswith("回复 @"):
            parts = re.split(r"(?m)^-{3,}\s*$", content, maxsplit=1)
            if len(parts) != 2:
                return None
            content = parts[1]
        content = "\n".join(line for line in content.splitlines()
                            if not line.lstrip().startswith(">"))
        # 大饼目前按照周期模型拟合曲线在走。做多策略：75550做多
        content = re.sub(
            r"(?m)^([A-Za-z]+|[\u4e00-\u9fff]+?)目前[^。\n]*。((?:做多|做空)策略:)",
            r"\1\2", content,
        )
        # Sol做多策略：100做多 / 大饼短线多单策略，轻仓：6.42w做多
        # bnb个人策略：做多思路类似，720-725做多
        headers = list(re.finditer(
            r"(?:^|\n)(?:个人)?([A-Za-z]+|[\u4e00-\u9fff]+?)"
            r"(?:个人)?(?:超短线|短线|空单|多单|做多|做空|分批做空)*策略"
            r"(?:改为)?(?:[，,]轻仓)?\s*[:,，]", content,
        ))
        if len(headers) != 1:
            return None
        header = headers[0]
        body = content[header.end():]
        n = self.NUMBER
        # 止损94.5 / 2250止损 / 6.8w止损
        stops = list(re.finditer(
            rf"止损\s*:?\s*({n})([万wW]?)|({n})([万wW]?)\s*止损(?!\s*:?\s*\d)", body,
        ))
        # 目标一105.5 / 目标2500 / 目标二，2600 / 止盈一12
        targets = list(re.finditer(
            rf"(?:目标|止盈)[一二三四五六七八九]*\s*[:，,]?\s*({n})([万wW]?)", body,
        ))
        if not stops or not targets:
            return None
        # 后面的行情评论不参与入场识别，也不从“待定”中猜价格。
        entry_text = body[:min(stops[0].start(), targets[0].start())]
        # 2320做多（最后的强支撑） / 8.81w（强阻力位）第二批加空
        entry_text = re.sub(r"[（(][^）)]*[）)]", "", entry_text)
        # 2455-2510分批做多 / 6.56w-6.7w分批做空
        # 现价8.55w这里第一批现价做空，8.81w第二批加空
        entry_pattern = (
            rf"({n})([万wW]?)(?:\s*[-—~～]\s*(?:现价)?({n})([万wW]?))?"
            r"(?:附近)?(?:这里)?(?:第一批|第二批)?(?:现价)?(?:分批)?(?:做多|做空|加仓多|加空)"
        )
        entries = list(re.finditer(entry_pattern, entry_text))
        # 二饼短线策略：做空2080 / 以太坊做空策略：做空点位在2850附近
        if not entries:
            entries = list(re.finditer(rf"(?:做多|做空)(?:点位在)?\s*({n})([万wW]?)", entry_text))
        # 标普指数短线做多策略：7500-现价7680附近，分批买入。
        if not entries:
            entries = list(re.finditer(
                rf"({n})([万wW]?)\s*[-—~～]\s*(?:现价)?({n})([万wW]?)附近[，,]\s*分批买入", entry_text,
            ))
        if not entries:
            return None
        # 空单保留的同时，轻仓做多：6.02w做多
        # 方向取策略标题或价格旁的开仓动作，不把对冲仓位的描述当成本次方向。
        side_text = header[0] if re.search(r"做多|多单|做空|空单", header[0]) else " ".join(e[0] for e in entries)
        long = bool(re.search(r"做多|多单|加仓多", side_text))
        short = bool(re.search(r"做空|空单|加空", side_text))
        if long == short:
            return None
        scale = Decimal(10000) if re.search(rf"{n}\s*[万wW]", entry_text +
                                          stops[0][0] + " ".join(t[0] for t in targets)) else Decimal(1)

        def price(value: str, unit: str) -> Decimal:
            amount = Decimal(value)
            return amount * (Decimal(10000) if unit else scale if amount < 100 else Decimal(1))

        prices = []
        for entry in entries:
            prices.append(price(entry[1], entry[2]))
            if entry.lastindex == 4:
                prices.append(price(entry[3], entry[4]))
        stop = stops[0]
        signal = TradeSignal(
            signal_time, header[1], tuple(prices), Direction.LONG if long else Direction.SHORT,
            tuple(price(t[1], t[2]) for t in targets),
            price(stop[1] or stop[3], stop[2] if stop[1] else stop[4]), source_id,
        )
        self._validate(signal)
        return signal
