# Discord Trade

接收 Discord 消息并存入 SQLite，按频道解析交易信号，发送飞书个人确认卡片。点击确认后通过 Bitget API 下单，执行结果回写数据库和卡片。

## 安装与运行

需要 Python 3.10+，Discord 账号需有目标频道的访问权限。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/credentials.example.py config/credentials.py
```

已有凭据文件时不要重复复制覆盖。填写配置后，从项目根目录启动：

```sh
python listener.py
```

程序同时启动 Discord 监听和飞书长连接回调，按 `Ctrl+C` 退出。飞书应用需启用长连接卡片回传交互、发送和更新消息权限，并发布配置。`FEISHU_RECEIVE_ID` 必须为接收人的 `open_id`；只有该用户可以操作卡片。

## 配置

| 文件 | 内容 |
| --- | --- |
| `config/app.py` | HTTP 代理、数据库路径、日志级别和滚动策略 |
| `config/credentials.py` | Discord、飞书、Bitget 凭据及 Bitget 模拟交易标志，不提交仓库 |
| `config/trading.py` | 交易开关、品种别名、频道仓位和 CFD 市价阈值 |

`HTTP_PROXY` 用于 Discord 和 Bitget REST 请求，飞书 SDK 使用自身网络连接。`TRADING_ENABLED=False` 时确认按钮不会下单，信号保持待确认。`BITGET_DEMO` 决定 Bitget 请求是否带模拟交易标志。

日志输出到终端和 `logs/listener.log`。`LOG_LEVEL` 控制级别；`LOG_ROLLING_MODE` 为 `time` 时按时间滚动，为 `size` 时按 `LOG_MAX_BYTES` 滚动；`LOG_BACKUP_COUNT` 控制备份数量。时间滚动使用 UTC。数据库和日志目录自动创建。

## 流程与规则

```text
接收消息 → 保存消息 → 解析信号 → 保存待确认信号 → 飞书卡片
                                                        ↓
                                           确认下单 / 忽略
                                                        ↓
                                           保存结果并更新卡片
```

- 所有 `on_message` 收到的消息都入库，仅注册频道进行信号解析。不拉取历史消息，不解析图片或 embed，但保存附件和 embed 元数据。
- 回复规则：首行包含 Markdown 格式的 Discord 消息链接，且链接频道 ID 等于当前频道 ID，才提取为 `reply_to_url`。入库正文移除首行及随后开头的回车、换行，保留正文内部换行。
- 信号保留原品种名称，交易前转大写并映射别名。价格使用 `Decimal`，JSON 中存字符串，信号时间使用北京时间。
- 至少有一个数字 TP；忽略 `OPEN`、`LATER`、待定目标。价格顺序校验失败抛出异常，不排序修正。
- 卡片永久有效；重复确认通过数据库原子状态更新拦截。忽略后不能再确认。
- 合约使用 Bitget UTA V3：固定名义金额分配到各入场点，统一限价，每单附带 SL 和 TP1。账户需事先设好全仓、双向持仓和杠杆；程序不设置杠杆。
- CFD 只处理黄金 `XAUUSD.s`：固定手数；确认后查询买卖报价，距离入场价不超过阈值时市价，否则限价。每个入场点独立下单，使用 TP1 全平。当前接普通 CFD 账户，不支持 CFD 带单账户。
- 成功表示交易所已接单，不表示限价单已成交。多笔请求按顺序提交，发生异常停止；请求发出后异常标记为结果待确认，不自动重试或撤销已成功的订单。

频道解析器在 `listener.py` 注册；交易参数在 `config/trading.py` 配置：

| 频道 ID | 解析内容 | 交易类型 |
| --- | --- | --- |
| `1295531142912413852` | 舒琴中文信号 | 合约 |
| `1386949813743915029` | 日内交易信号 | 合约 |
| `1464406516282167448` | 相会员群文字策略 | 合约 |
| `1488133240975003761` | PREMIUM SIGNALS 黄金及外汇 | 仅黄金 CFD |

## 数据与目录

SQLite 路径默认为 `data/discord_trade.sqlite3`，相对路径以项目根目录为基准。无需额外数据库服务，没有外键和历史迁移逻辑。

- `discord_messages`：消息、来源、作者、回复链接、附件和时间，`message_id` 为主键，`message_url` 唯一。回复列表按 `reply_to_url` 查询。
- `trade_signals`：以原消息 `message_id` 为主键，保存信号 JSON、状态、飞书消息 ID、执行结果和时间。
- 状态：`pending` 待确认、`ignored` 已忽略、`executing` 执行中、`failed` 执行失败、`succeeded` 执行成功、`uncertain` 结果待确认。启动时将遗留执行中状态转为结果待确认。
- 重复消息不重复生成信号和通知。卡片发送失败时信号仍保存，当前没有自动补发；待核实订单需要人工查看 Bitget。

| 路径 | 用途 |
| --- | --- |
| `listener.py` | 启动、监听消息、解析分发、发送卡片 |
| `parsers/` | 信号实体、解析基类、按频道实现 |
| `storage/` | 消息实体、SQLite 表和存取方法 |
| `notifications/` | 飞书 SDK 封装、卡片、回调与后台执行 |
| `trading/` | 订单计划、合约/CFD 执行器、Bitget REST |
| `tests/` | 单元测试、明确开启才运行的外部集成测试 |
| `csv/` | 历史导出，供分析和部分解析测试使用 |

项目使用 Python 命名空间包，不需要 `__init__.py`，直接从具体模块导入。`__pycache__/` 是自动生成的字节码缓存，可以删除，运行后可能重新生成，已忽略提交。

## 测试

普通测试不发送外部消息、不下单：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

部分解析测试依赖 `csv/` 历史导出。外部集成测试需要本地凭据，默认跳过。

真实 SOL 交互挂单：先启动 `listener.py`，再在另一终端执行：

```sh
RUN_FEISHU_INTEGRATION=1 .venv/bin/python -m unittest tests.test_feishu_integration.FeishuIntegrationTest.test_send_sol_live_order_card -v
```

命令只发送卡片。点击确认后，限价 100 买入 1 SOL（100 USDT 名义金额），同时设置 TP 105.5、SL 94.5。专用 `test-sol` 配置不影响正式频道仓位。每次执行会创建新的独立卡片。

仅测试飞书交互、不允许下单的卡片：

```sh
RUN_FEISHU_INTEGRATION=1 .venv/bin/python -m unittest tests.test_feishu_integration.FeishuIntegrationTest.test_send_confirmation_card -v
```

`tests/test_bitget_integration.py` 为直接下单测试，设置 `RUN_BITGET_INTEGRATION=1` 才执行，开启后不经过飞书确认。
