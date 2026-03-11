"""Logging configuration for the FastAPI backend."""

import logging
import sys
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler
from pathlib import Path

from uvicorn.logging import ColourizedFormatter


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the ``app`` logger hierarchy with console and rotating file handlers.

    Uses a named logger (``app``) instead of the root logger so that
    uvicorn's own logging configuration is not disturbed.

    Args:
        log_level: The logging level name (e.g. "DEBUG", "INFO", "WARNING").
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Resolve project root (4 levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "backend.log"

    app_logger = logging.getLogger("app")
    app_logger.setLevel(numeric_level)

    # Clear existing handlers to avoid duplicates on reload
    app_logger.handlers.clear()

    # Rotating file handler — 10 MB max, keep 5 backups
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    app_logger.addHandler(file_handler)

    # Console handler — use uvicorn's colored formatter when available
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    try:
        from uvicorn.logging import ColourizedFormatter
        console_formatter = ColourizedFormatter(fmt="%(levelprefix)s %(asctime)s - %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", use_colors=True,)
    except ImportError:
        console_formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)

    app_logger.info("Logging initialized (level=%s, file=%s)", log_level.upper(), log_file)

# class CustomFormatter(ColourizedFormatter):
#     def formatMessage(self, record):
#         # remove uvicorn's padded levelprefix
#         record.levelprefix = record.levelname
#         return super().formatMessage(record)
#
#
# def setup_logging(log_level: str = "INFO"):
#     dictConfig(
#         {
#             "version": 1,
#             "disable_existing_loggers": False,
#             "formatters": {
#                 "default": {
#                     "()": CustomFormatter,
#                     "fmt": "%(levelprefix)s %(asctime)s | %(name)s | %(message)s",
#                     "datefmt": "%Y-%m-%d %H:%M:%S",
#                     "use_colors": True,
#                 },
#             },
#             "handlers": {
#                 "console": {
#                     "class": "logging.StreamHandler",
#                     "formatter": "default",
#                 },
#             },
#             "loggers": {
#                 "": {
#                     "handlers": ["console"],
#                     "level": log_level,
#                 },
#                 "uvicorn": {
#                     "level": log_level,
#                 },
#                 "uvicorn.error": {
#                     "level": log_level,
#                 },
#                 "uvicorn.access": {
#                     "handlers": ["console"],
#                     "level": log_level,
#                     "propagate": False,
#                 },
#             },
#         }
#     )
