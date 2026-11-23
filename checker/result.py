"""Формирование результата: общий список нарушений и вердикт."""
from .explain import place_text

PASS = "допущена"
FAIL = "на доработку"


def make_violation(rule, expected, actual, places, count, checked, fact_text=None, conclusion=None):
    """Единый формат нарушения. В отчёте не более 5 мест, общее число — в count."""
    return {
        "rule_id": rule["id"], "name": rule["name"], "type": rule["type"],
        "expected": expected, "actual": actual,
        "count": count, "checked": checked, "places": places[:5],
        "fact_text": fact_text, "conclusion": conclusion,
    }


def build_result(violations, profile, filename):
    violations = sorted(violations, key=lambda v: v["rule_id"])
    return {
        "status": "ok",
        "verdict": FAIL if violations else PASS,
        "violations": violations,
        "message": (f"Найдено нарушений: {len(violations)}. Работа возвращается на доработку."
                    if violations else "Нарушений не найдено. Работа допускается к содержательной проверке."),
        "profile": profile,
        "file": filename,
        "from_cache": False,
    }


def error_result(kind, message, profile=None, filename=None):
    """Вместо вердикта — сообщение об ошибке."""
    return {"status": "error", "verdict": None, "violations": [], "message": message,
            "error_type": kind, "profile": profile, "file": filename, "from_cache": False}


def format_text(result):
    """Текстовый отчёт для консоли."""
    lines = [f"Файл: {result.get('file')}", f"Вид оформления: {result.get('profile')}"]
    if result["status"] == "error":
        lines.append(f"ОШИБКА ({result.get('error_type')}): {result['message']}")
        return "\n".join(lines)
    lines.append(f"Вердикт: {result['verdict']}" + (" (результат из кэша)" if result.get("from_cache") else ""))
    lines.append(result["message"])
    for i, v in enumerate(result["violations"], 1):
        lines.append("")
        lines.append(f"{i}. [{v['rule_id']}] {v['name']}")
        lines.append(f"   Ожидалось: {v['expected']}")
        lines.append(f"   Фактически: {v['actual']}")
        lines.append(f"   Мест с нарушением: {v['count']} (показаны первые {len(v['places'])})")
        for p in v["places"]:
            lines.append(f"     - {place_text(p)}")
        lines.append("   Объяснение:")
        for step in v["explanation"]:
            lines.append(f"     {step}")
    return "\n".join(lines)
