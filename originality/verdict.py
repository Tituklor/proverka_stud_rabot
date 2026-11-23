"""Вердикт по результату проверки."""
from .rules import is_within_threshold

ADMITTED = "Допущена к содержательной проверке"
RETURNED = "Возвращена на доработку"


def make_verdict(info, threshold_percent):
    """Допуск, если процент заимствований не превышает порог (граница включается)."""
    admitted = is_within_threshold(info["matched"], info["total"], threshold_percent)
    return {"admitted": admitted, "verdict": ADMITTED if admitted else RETURNED}
