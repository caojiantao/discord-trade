"""集中配置项目日志，提供类似 Logback 的级别和滚动文件能力。"""

import logging
import logging.config
from pathlib import Path


def configure_logging(config) -> None:
    log_file = Path(config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    mode = getattr(config, "LOG_ROLLING_MODE", "time")

    if mode == "size":
        handler = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_file),
            "maxBytes": config.LOG_MAX_BYTES,
            "backupCount": config.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
        }
    else:
        handler = {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(log_file),
            "when": config.LOG_ROLLING_WHEN,
            "interval": config.LOG_ROLLING_INTERVAL,
            "backupCount": config.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
            "utc": True,
        }

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s %(levelname)s %(name)s - %(message)s",
            },
        },
        "handlers": {
            "file": {**handler, "formatter": "standard"},
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": config.LOG_LEVEL,
            "handlers": ["file", "console"] if config.LOG_CONSOLE else ["file"],
        },
    })
