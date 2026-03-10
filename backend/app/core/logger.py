"""Logging configuration for the FastAPI backend."""

import logging
import sys
from pathlib import Path


def setup_logging(log_level: int = logging.INFO) -> None:
    """Configure root logger with console and file handlers.

    Args:
        log_level: The logging level (e.g., logging.DEBUG, logging.INFO).
    """
    # Resolve project root (4 levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "backend.log"

    numeric_level = log_level

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()

    # File handler - detailed format, append mode
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler - simple format
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root_logger.info("Logging initialized - log file: %s", log_file)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
    """
    return logging.getLogger(name)
