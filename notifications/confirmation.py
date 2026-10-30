"""飞书个人确认卡片与长连接回调。"""

import json
import logging
from zoneinfo import ZoneInfo
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

from config.notifications import CHANNEL_FEISHU_CHATS
from storage.database import Database


def build_signal_card(message_id: str, signal: dict, status: str = "pending", *,
                      channel_id: str | int | None = None) -> dict:
    labels = {"pending": "待确认", "ignored": "已忽略", "executing": "执行中",
              "failed": "执行失败", "succeeded": "执行成功", "uncertain": "结果待确认"}
    # 首次发送和回调更新都按来源频道读取名称，避免更新卡片后丢失频道名。
    channel = CHANNEL_FEISHU_CHATS.get(int(channel_id), {}) if str(channel_id).isdigit() else {}
    title = " · ".join(filter(None, ["交易信号", channel.get("name"), labels[status]]))
    time = datetime.fromisoformat(signal["signal_time"]).astimezone(ZoneInfo("Asia/Shanghai"))
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content":
        f"**品种**：{signal['symbol']}\n"
        f"**方向**：{'做多' if signal['direction'] == 'long' else '做空'}\n"
        f"**时间**：{time:%Y-%m-%d %H:%M:%S}（北京时间）\n"
        f"**入场**：{' / '.join(signal['entry_prices'])}\n"
        f"**止盈（TP1 全平）**：{signal['take_profits'][0]}\n"
        f"**止损**：{signal['stop_loss']}\n"
        f"[原消息]({signal['source_id']})"}}]
    if status == "pending":
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": label},
             "type": style, "value": {"action": action, "message_id": message_id}}
            for action, label, style in [("confirm", "确认开仓", "primary"), ("ignore", "忽略", "default")]
        ]})
    return {"config": {"wide_screen_mode": True, "update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": title},
                       "template": "blue" if status == "pending" else "grey"},
            "elements": elements}


class ConfirmationHandler:
    def __init__(self, database: Database, allowed_open_id: str, *,
                 notifier=None, bitget=None, channel_config=None, mapping=None, enabled=False):
        self.database = database
        self.allowed_open_id = allowed_open_id
        self.notifier = notifier
        self.bitget = bitget
        self.channel_config = channel_config or {}
        self.mapping = mapping or {}
        self.enabled = enabled
        self.workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trade-confirmation")

    def handle(self, data):
        try:
            event = data.event
            if event.operator.open_id != self.allowed_open_id:
                return self._toast("error", "你没有此信号的操作权限")
            value = event.action.value or {}
            message_id = value.get("message_id")
            action = value.get("action")
            if not isinstance(message_id, str) or action not in {"confirm", "ignore"}:
                return self._toast("error", "无效操作")
            row = self.database.get_signal(message_id)
            if row is None:
                return self._toast("error", "信号不存在")
            if row["status"] != "pending":
                return self._toast("info", "信号已处理，请勿重复操作")
            logging.info("feishu_card_action action=%s message_id=%s operator=%s",
                         action, message_id, event.operator.open_id)
            if row["status"] == "pending" and action == "confirm":
                if not self.enabled or self.bitget is None:
                    return self._toast("info", "交易开关未开启，不会下单")
                if json.loads(row["signal_json"])["source_id"].startswith("urn:discord-trade:test:"):
                    return self._toast("error", "这是旧版交互测试卡片，不允许实盘下单")
                # 原子取得执行权后立即返回；交易请求不阻塞飞书回调。
                if not self.database.transition(message_id, "pending", "executing"):
                    return self._toast("info", "信号已处理，请勿重复确认")
                try:
                    self.workers.submit(self._execute, message_id)
                except Exception:
                    self.database.transition(message_id, "executing", "failed",
                                             result={"error": "后台任务提交失败，未下单"})
                    raise
                return self._toast("info", "已确认，正在提交订单")
            if action == "ignore":
                if not self.database.transition(message_id, "pending", "ignored"):
                    return self._toast("info", "信号已处理，请勿重复操作")
                row = self.database.get_signal(message_id)
            return P2CardActionTriggerResponse({
                "toast": {"type": "info", "content": "信号已处理"},
                "card": {"type": "raw", "data": build_signal_card(
                    message_id, json.loads(row["signal_json"]), row["status"],
                    channel_id=row["channel_id"])},
            })
        except Exception:
            logging.exception("feishu_card_action_failed")
            return self._toast("error", "处理失败，请查看程序日志")

    def _update_card(self, message_id):
        if self.notifier is None:
            return
        row = self.database.get_signal(message_id)
        if not row["feishu_message_id"]:
            return
        card = build_signal_card(message_id, json.loads(row["signal_json"]), row["status"],
                                 channel_id=row["channel_id"])
        if row["result_json"]:
            card["elements"].append({"tag": "div", "text": {"tag": "plain_text",
                                     "content": f"执行结果：{row['result_json']}"}})
        try:
            self.notifier.update_card(row["feishu_message_id"], card)
        except Exception:
            # 通知失败不改变已保存的交易结果，更不能触发重复下单。
            logging.exception("feishu_card_update_failed message_id=%s", message_id)

    def _execute(self, message_id):
        from trading.execution import build_order_plan
        self._update_card(message_id)
        results = []
        request_started = False
        try:
            row = self.database.get_signal(message_id)
            plan = build_order_plan(row, self.channel_config, self.mapping, self.bitget)
            logging.info("trade_plan message_id=%s plan=%s", message_id, plan)
            for order in plan.orders:
                request_started = True
                response = (self.bitget.place_futures_order(order) if plan.market == "futures"
                            else self.bitget.place_cfd_order(order))
                results.append(response)
            status = "succeeded"
            result = {"orders": results}
        except Exception as error:
            # 请求发出后的异常可能代表交易所已经接单；保留结果并禁止自动重试。
            status = "uncertain" if request_started else "failed"
            result = {"orders": results, "error": str(error)}
            logging.exception("trade_execution_failed message_id=%s status=%s", message_id, status)
        self.database.transition(message_id, "executing", status, result=result)
        self._update_card(message_id)

    @staticmethod
    def _toast(kind: str, content: str):
        return P2CardActionTriggerResponse({"toast": {"type": kind, "content": content}})


def run_confirmation_listener(app_id: str, app_secret: str, database_path: str, open_id: str):
    """在独立进程运行 SDK 事件循环，避免与 Discord 的 asyncio 循环冲突。"""
    from config import app, credentials, trading as trading_config
    from logging_setup import configure_logging
    from notifications.feishu import FeishuNotifier
    from trading.bitget import BitgetClient
    configure_logging(app)
    handler = ConfirmationHandler(
        Database(database_path), open_id,
        notifier=FeishuNotifier(app_id, app_secret),
        bitget=BitgetClient(credentials.BITGET_API_KEY, credentials.BITGET_API_SECRET,
                            credentials.BITGET_API_PASSPHRASE, demo=credentials.BITGET_DEMO,
                            proxy=app.HTTP_PROXY),
        channel_config=trading_config.CHANNEL_TRADING_CONFIG,
        mapping=trading_config.TRADE_SYMBOL_MAPPING, enabled=trading_config.TRADING_ENABLED,
    )
    dispatcher = lark.EventDispatcherHandler.builder("", "").register_p2_card_action_trigger(handler.handle).build()
    lark.ws.Client(app_id, app_secret, event_handler=dispatcher).start()
