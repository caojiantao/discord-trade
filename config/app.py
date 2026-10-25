"""程序运行配置。"""

HTTP_PROXY = "http://127.0.0.1:7890"  # 不使用代理时设为 None

DATABASE_PATH = "data/discord_trade.sqlite3"  # 相对路径以项目根目录为基准

LOG_LEVEL = "DEBUG"
LOG_FILE = "logs/listener.log"
LOG_CONSOLE = True
LOG_ROLLING_MODE = "time"
LOG_ROLLING_WHEN = "midnight"
LOG_ROLLING_INTERVAL = 1
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 7

