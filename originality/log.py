"""Простой лог хода проверки в файл."""
import logging
from pathlib import Path

_current_path = None


def get_logger(log_path):
    global _current_path
    logger = logging.getLogger("originality")
    logger.setLevel(logging.INFO)
    if _current_path != log_path:
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _current_path = log_path
    return logger
