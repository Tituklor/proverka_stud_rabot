"""Простой лог хода проверки в файл check.log."""
import logging
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "check.log"


def get_logger():
    log = logging.getLogger("format_checker")
    if not log.handlers:  # чтобы не добавлять обработчик повторно
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log
