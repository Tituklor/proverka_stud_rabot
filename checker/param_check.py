"""Часть 1: проверка параметров оформления (правила типа parameter)."""
from .knowledge import describe_expected
from .result import make_violation

EPS = 1e-9  # защита от погрешности чисел с плавающей точкой

# Какие роли абзацев попадают в область действия правила
SCOPES = {
    "body": {"body"},
    "headings": {"heading"},
    "non_title": {"body", "heading", "toc"},
    "document": {"document"},
}


def in_range(rule, x):
    """Проверка числа по диапазону с учётом включения границ и допуска.

    Включённая граница: значение в пределах допуска от неё допустимо.
    Исключённая граница: значение в пределах допуска от неё считается «на границе» и недопустимо.
    """
    tol = rule.get("tolerance", 0)
    lo, hi = rule["min"], rule["max"]
    if lo is not None:
        if rule["include_min"]:
            if x < lo - tol - EPS:
                return False
        elif x <= lo + tol + EPS:
            return False
    if hi is not None:
        if rule["include_max"]:
            if x > hi + tol + EPS:
                return False
        elif x >= hi - tol - EPS:
            return False
    return True


def matches(rule, value):
    if rule["condition"] == "equals":
        return value == rule["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False  # например «фиксированный 18 пт» не может быть в числовом диапазоне
    return in_range(rule, value)


def fmt(value, rule):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}" + (f" {rule['unit']}" if rule.get("unit") else "")
    return str(value)


def check_params(facts, kb):
    violations = []
    for fact_type, observations in facts.items():
        for rule in kb.rules_for(fact_type):  # только правила, применимые к этому факту
            roles = SCOPES.get(rule["scope"], set())
            scoped = [o for o in observations if o["role"] in roles]
            bad = [o for o in scoped if not matches(rule, o["value"])]
            if not bad:
                continue
            distinct = list(dict.fromkeys(fmt(o["value"], rule) for o in bad))
            actual = "; ".join(distinct[:3]) + ("…" if len(distinct) > 3 else "")
            note = next((o["note"] for o in bad if o.get("note")), None)
            if note:
                actual += f" ({note})"
            places = [dict(o["place"], value=fmt(o["value"], rule)) for o in bad]
            violations.append(make_violation(rule, describe_expected(rule), actual, places, len(bad), len(scoped)))
    return violations
