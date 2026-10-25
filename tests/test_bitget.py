import base64
import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

from trading.bitget import BitgetClient


class BitgetClientTest(unittest.TestCase):
    def test_get_cfd_ticker_query_and_signature(self):
        client = BitgetClient("key", "secret", "passphrase")
        result = {"code": "00000", "data": [
            {"symbol": "XAUUSD.s", "ask1": "4538.60", "bid1": "4538.50", "quoteTime": "1000"},
        ]}
        client.opener = MagicMock()
        client.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(result).encode()

        with patch("trading.bitget.time.time", return_value=1):
            self.assertEqual(client.get_cfd_ticker("XAUUSD.s"), result)

        request = client.opener.open.call_args.args[0]
        path = "/api/v3/cfd/market/tickers?symbol=XAUUSD.s"
        self.assertEqual(request.full_url, "https://api.bitget.com" + path)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        signature = base64.b64encode(hmac.new(
            b"secret", ("1000GET" + path).encode(), hashlib.sha256,
        ).digest()).decode()
        self.assertEqual(request.get_header("Access-sign"), signature)
