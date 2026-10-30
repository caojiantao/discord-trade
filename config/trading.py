"""交易品种和频道交易参数。"""

TRADING_ENABLED = True
TRADE_SYMBOL_MAPPING = {
    # 这里只配置名称不同的别名；BTC、ETH、AAPL 等同名品种会直接转大写。
    "比特币": "BTC",
    "黄金": "XAU",
    "GOLD": "XAU",
}

CHANNEL_TRADING_CONFIG = {
    # 专用于飞书 SOL 实盘测试卡片，止损预算 5.5 USDT（对应 100 USDT 名义仓位），不影响正式频道仓位。
    "test-sol": {"executor": "futures", "max_loss_usdt": "5.5"},
    1295531142912413852: {"executor": "futures", "max_loss_usdt": "20"},
    1386949813743915029: {"executor": "futures", "max_loss_usdt": "20"},
    1464406516282167448: {"executor": "futures", "max_loss_usdt": "20"},
    1488133240975003761: {"executor": "cfd", "lots": "0.01", "threshold": "3"},
}
