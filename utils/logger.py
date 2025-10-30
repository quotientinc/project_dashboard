"""
Logging configuration for the Project Management Dashboard.

This module sets up logging to both console and file outputs, ensuring all
application logs are captured in the logs/ directory while maintaining
console output for streamlit run commands.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_level=logging.INFO):
    """
    Configure logging for the application.

    Sets up dual output:
    - Console handler: for streamlit run output (same as before)
    - File handler: for persistent logs in logs/ directory

    Args:
        log_level: The logging level (default: logging.INFO)

    Returns:
        logging.Logger: Configured root logger
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"dashboard.log"

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )

    # Console handler (for streamlit run output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (for persistent logs) - mode='w' creates a fresh file each restart
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Log the initialization
    logger.info(f"Logging initialized. Log file: {log_file}")
    logger.info(f"Log level: {logging.getLevelName(log_level)}")

    # Configure Streamlit's internal loggers to use our handlers
    try:
        import streamlit.logger

        # Get Streamlit's root logger
        st_logger = streamlit.logger.get_logger(__name__)

        # Configure all Streamlit loggers to propagate to root logger
        for logger_name in logging.root.manager.loggerDict:
            if logger_name.startswith('streamlit'):
                st_log = logging.getLogger(logger_name)
                st_log.propagate = True
                # Add our file handler to Streamlit loggers
                if not any(isinstance(h, logging.FileHandler) for h in st_log.handlers):
                    st_log.addHandler(file_handler)
    except ImportError:
        logger.warning("Could not import streamlit.logger - Streamlit logs may not be captured")
    except Exception as e:
        logger.warning(f"Could not configure Streamlit logging: {e}")

    return logger


def get_logger(name):
    """
    Get a logger instance for a specific module.

    Args:
        name: The name of the logger (typically __name__)

    Returns:
        logging.Logger: Logger instance for the specified module
    """
    return logging.getLogger(name)