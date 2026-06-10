from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import colorlog
except ImportError:  # pragma: no cover - colorlog is an optional runtime extra
    colorlog = None  # type: ignore[assignment]

_LOG_DIR_NAME = "logs"
_DEFAULT_LOG_FILE = "datalight.log"
_ROOT_LOGGER_NAME = "datalight"
_CONFIGURED = False

_FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(filename)s:%(funcName)s:%(lineno)d - %(message)s"
)
_CONSOLE_FORMAT = (
    "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s:%(filename)s:%(funcName)s:%(lineno)d - %(message)s%(reset)s"
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def log_dir() -> Path:
    return project_root() / _LOG_DIR_NAME


def setup_logging(
    *,
    level: str | int = logging.INFO,
    log_file: str | None = None,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure the global datalight logger once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(level)
    root_logger.propagate = False

    if console:
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(level)
        if colorlog is not None:
            console_handler.setFormatter(
                colorlog.ColoredFormatter(
                    _CONSOLE_FORMAT,
                    datefmt="%Y-%m-%d %H:%M:%S",
                    log_colors={
                        "DEBUG": "blue",
                        "INFO": "white",
                        "WARNING": "yellow",
                        "ERROR": "red",
                        "CRITICAL": "red,bg_white",
                    },
                ),
            )
        else:
            console_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(console_handler)

    log_path = log_dir()
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / (log_file or _DEFAULT_LOG_FILE),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root_logger.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured logger. Child loggers propagate records to the datalight root."""
    setup_logging()
    if not name:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    if name.startswith(_ROOT_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


logger = get_logger()
