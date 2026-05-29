"""操作日志与 Flask 请求日志。"""
import csv
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any

_LOG_DIR = os.path.join(os.path.dirname(__file__), "generated")
_OPERATION_LOG = os.path.join(_LOG_DIR, "operation_log.csv")
_APP_LOG = os.path.join(_LOG_DIR, "app.log")

_CSV_HEADER = [
    "timestamp",
    "user_text",
    "source",
    "skill",
    "params",
    "result",
    "error_message",
    "duration_ms",
]

_csv_lock = threading.Lock()


def _ensure_log_dir() -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)


def _params_summary(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        if isinstance(v, list):
            parts.append(f"{k}=[{','.join(str(x) for x in v[:3])}{'...' if len(v) > 3 else ''}]")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def log_operation(
    *,
    user_text: str,
    source: str | None,
    skill: str | None,
    params: dict[str, Any] | None,
    result: str,  # "planned" | "success" | "error"
    error_message: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Append one row to operation_log.csv (thread-safe)."""
    _ensure_log_dir()
    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_text": user_text,
        "source": source or "",
        "skill": skill or "",
        "params": _params_summary(params),
        "result": result,
        "error_message": (error_message or "").replace("\n", " | "),
        "duration_ms": str(duration_ms),
    }
    file_exists = os.path.isfile(_OPERATION_LOG)
    with _csv_lock:
        with open(_OPERATION_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


def setup_flask_logger(app_name: str = "cobot_web") -> logging.Logger:
    """Configure Flask app.logger with a rotating file handler.

    Call this once before app.run().
    """
    _ensure_log_dir()
    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-load
    if any(isinstance(h, RotatingFileHandler) and h.baseFilename == _APP_LOG for h in logger.handlers):
        return logger

    handler = RotatingFileHandler(
        _APP_LOG,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also log to stdout
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console)

    return logger
