"""Bitget V3 原生 REST 客户端，支持统一账户合约和 CFD。

这里只负责把订单计划转换成 Bitget 请求；是否真正发送由调用方的交易开关控制。
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from decimal import Decimal

from .models import EntryOrderPlan


class BitgetClient:
    """Bitget USDT 永续及 CFD 交易、行情客户端。"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        *,
        demo: bool = False,
        proxy: str | None = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = "https://api.bitget.com"
        self.demo = demo
        # Bitget REST 请求和 Discord 一样，可以通过本地 HTTP 代理转发。
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else urllib.request.ProxyHandler()
        )

    def _request(self, method: str, path: str, body: dict) -> dict:
        method = method.upper()
        # GET 参数放入 URL，并连同查询字符串参与签名；请求体必须为空。
        if method == "GET":
            query = urllib.parse.urlencode(body)
            if query:
                path = f"{path}?{query}"
            payload = ""
        else:
            payload = json.dumps(body, separators=(",", ":"))
        timestamp = str(int(time.time() * 1000))
        prehash = timestamp + method.upper() + path + payload
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()
        ).decode()
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "zh-CN",
        }
        if self.demo:
            headers["X-SIMULATED-TRADING"] = "1"
        request = urllib.request.Request(
            self.base_url + path, data=payload.encode() if payload else None, headers=headers, method=method
        )
        method = method.upper()
        logging.info("bitget_api_request method=%s path=%s body=%s", method, path, body)
        try:
            with self.opener.open(request, timeout=15) as response:
                result = json.loads(response.read().decode())
        except HTTPError as error:
            # Bitget 的 400/401/403 响应通常包含具体错误码，必须保留响应体便于排查。
            raw_body = error.read().decode("utf-8", errors="replace")
            logging.error(
                "bitget_api_http_error status=%s method=%s path=%s body=%s",
                error.code, method, path, raw_body,
            )
            raise RuntimeError(f"Bitget HTTP {error.code}: {raw_body}") from error
        logging.info("bitget_api_response method=%s path=%s response=%s", method, path, result)
        if result.get("code") != "00000":
            raise RuntimeError(f"Bitget 请求失败：{result}")
        return result

    def place_futures_order(self, order: EntryOrderPlan) -> dict:
        # 账户已经统一设置为全仓 20 倍，这里不再重复调用设置杠杆接口。
        # size 使用实际仓位数量，不是保证金金额，也不是名义金额。
        body = {
            "symbol": order.symbol,
            "category": "USDT-FUTURES",
            # 账户已经统一使用全仓，订单请求也明确声明为 crossed。
            "marginMode": "crossed",
            "marginCoin": "USDT",
            # 统一账户 V3 下单接口使用 qty 表示实际下单数量。
            "qty": str(order.quantity),
            "side": order.side,
            # 账户使用双向持仓，开仓时按买卖方向指定 long 或 short。
            "posSide": "long" if order.side == "buy" else "short",
            "orderType": order.order_type,
            "timeInForce": "GTC",
            # 统一账户 V3 使用 takeProfit / stopLoss，一次请求即可附带止盈止损。
            # 官方 V3 取值为 mark（标记价格）或 market（最新成交价）。
            "tpTriggerBy": "mark",
            "slTriggerBy": "mark",
            "takeProfit": str(order.take_profit),
            "stopLoss": str(order.stop_loss),
            "tpOrderType": "market",
            "slOrderType": "market",
        }
        if order.price is not None:
            body["price"] = str(order.price)
        # 统一账户必须使用 V3 交易接口，V2 mix 接口属于经典账户。
        return self._request("POST", "/api/v3/trade/place-order", body)

    def get_cfd_ticker(self, symbol: str) -> dict:
        """查询 CFD 行情；data 中的 ask1 / bid1 可用于计算买卖点差。"""
        # 使用账户实际品种代码，例如零手续费账户的 XAUUSD.s，保留后缀大小写。
        return self._request("GET", "/api/v3/cfd/market/tickers", {"symbol": symbol})

    def place_cfd_order(self, order: EntryOrderPlan) -> dict:
        """通过 Bitget CFD 专用接口下单，并在同一请求中设置止盈止损。"""
        body = {
            "symbol": order.symbol,
            "orderType": order.order_type,
            "side": order.side,
            "qty": str(order.quantity),
            "takeProfit": str(order.take_profit),
            "stopLoss": str(order.stop_loss),
        }
        if order.price is not None:
            body["price"] = str(order.price)
        return self._request("POST", "/api/v3/cfd/trade/place-order", body)
