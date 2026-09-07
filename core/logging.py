"""
Structured logging configuration for StockAI.
"""
import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return root stockai logger."""
    logger = logging.getLogger("stockai")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


log = setup_logging()
