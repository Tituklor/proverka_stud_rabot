"""Доступ к базе знаний: загрузка правил, индекс по параметру, поиск конфликтов."""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RULES_DIR = BASE_DIR / "rules"


class KnowledgeError(Exception):
    """kind: 'profile' (нет такого вида оформления), 'rules_format', 'rules_conflict'."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class KnowledgeBase:
    def __init__(self, data, path):
        self.path = path
        self.rules = data["rules"]
        self.by_id = {r["id"]: r for r in self.rules}
        # Индекс: тип параметра -> правила, которые к нему применимы
        self.by_param = {}
        for r in self.rules:
            if r["type"] == "parameter":
                self.by_param.setdefault(r["applies_to"], []).append(r)
        self.structure_rules = [r for r in self.rules if r["type"] == "structure"]
        self.structure_elements = sorted(data["structure_elements"], key=lambda e: e["order"])

    def rule(self, rule_id):
        return self.by_id.get(rule_id)

    def rules_for(self, param):
        return self.by_param.get(param, [])


def load_knowledge(profile, rules_dir=None):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", str(profile)):
        raise KnowledgeError("profile", f"Недопустимое имя вида оформления: «{profile}».")
    path = Path(rules_dir or DEFAULT_RULES_DIR) / f"{profile}.json"
    if not path.is_file():
        raise KnowledgeError("profile", f"Вид оформления «{profile}» не найден (нет файла {path.name}).")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise KnowledgeError("rules_format", f"Файл правил {path.name} не читается: {e}")

    _validate(data)
    problems = find_conflicts(data["rules"])
    if problems:
        raise KnowledgeError("rules_conflict",
                             "В базе знаний найден конфликт правил, вердикт не выносится: " + "; ".join(problems))
    return KnowledgeBase(data, path)


def _validate(data):
    """Проверяем, что у каждого правила есть обязательные поля (в т.ч. включение границ)."""
    if not isinstance(data, dict) or "rules" not in data or "structure_elements" not in data:
        raise KnowledgeError("rules_format", "В файле правил нет разделов «rules» и «structure_elements».")
    for r in data["rules"]:
        rid = r.get("id", "?")
        for key in ("id", "name", "type", "condition"):
            if key not in r:
                raise KnowledgeError("rules_format", f"Правило {rid}: нет поля «{key}».")
        if r["type"] == "parameter":
            for key in ("applies_to", "scope"):
                if key not in r:
                    raise KnowledgeError("rules_format", f"Правило {rid}: нет поля «{key}».")
            if r["condition"] == "equals":
                if "value" not in r:
                    raise KnowledgeError("rules_format", f"Правило {rid}: нет поля «value».")
            elif r["condition"] == "range":
                for key in ("min", "max", "include_min", "include_max"):
                    if key not in r:
                        raise KnowledgeError("rules_format",
                                             f"Правило {rid}: для диапазона нужно явно указать «{key}».")
                if r["min"] is None and r["max"] is None:
                    raise KnowledgeError("rules_format", f"Правило {rid}: диапазон без границ.")
            else:
                raise KnowledgeError("rules_format", f"Правило {rid}: неизвестное условие «{r['condition']}».")
        elif r["type"] == "structure":
            if r["condition"] not in ("required_present", "order"):
                raise KnowledgeError("rules_format", f"Правило {rid}: неизвестное условие «{r['condition']}».")
        else:
            raise KnowledgeError("rules_format", f"Правило {rid}: неизвестный тип «{r['type']}».")
    for e in data["structure_elements"]:
        for key in ("key", "name", "order", "required", "titles"):
            if key not in e:
                raise KnowledgeError("rules_format", f"Элемент структуры {e.get('key', '?')}: нет поля «{key}».")


def find_conflicts(rules):
    """Возвращает список текстовых описаний конфликтов (пустой, если конфликтов нет)."""
    problems = []
    ids = [r["id"] for r in rules]
    for rid in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"идентификатор {rid} повторяется")

    # Два правила к одному параметру в одной области действия (scope) не должны противоречить друг другу
    groups = {}
    for r in rules:
        if r["type"] == "parameter":
            groups.setdefault((r["applies_to"], r["scope"]), []).append(r)
    for (param, _scope), group in groups.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                msg = _pair_conflict(group[i], group[j])
                if msg:
                    problems.append(f"{group[i]['id']} и {group[j]['id']} (параметр «{param}»): {msg}")

    return problems


def _pair_conflict(a, b):
    if a["condition"] != b["condition"]:
        return "условия разных типов (значение и диапазон)"
    if a["condition"] == "equals":
        if a["value"] != b["value"]:
            return f"требуются разные значения: «{a['value']}» и «{b['value']}»"
        return None
    # Диапазоны: конфликт, если пересечение пустое (номинальные значения, без допуска)
    lo, inc_lo = _stricter_low(a, b)
    hi, inc_hi = _stricter_high(a, b)
    if lo is not None and hi is not None:
        if lo > hi or (lo == hi and not (inc_lo and inc_hi)):
            return "допустимые диапазоны не пересекаются"
    return None


def _stricter_low(a, b):
    cands = [(r["min"], r["include_min"]) for r in (a, b) if r["min"] is not None]
    if not cands:
        return None, True
    best = max(c[0] for c in cands)
    return best, all(c[1] for c in cands if c[0] == best)


def _stricter_high(a, b):
    cands = [(r["max"], r["include_max"]) for r in (a, b) if r["max"] is not None]
    if not cands:
        return None, True
    best = min(c[0] for c in cands)
    return best, all(c[1] for c in cands if c[0] == best)


def describe_expected(rule):
    """Текстовое описание требования правила (для отчёта и объяснения)."""
    if rule["condition"] == "equals":
        return f"«{rule['value']}»"
    unit = f" {rule['unit']}" if rule.get("unit") else ""
    tol = rule.get("tolerance", 0)
    lo, hi = rule["min"], rule["max"]
    inc = lambda flag: "включена" if flag else "не включена"
    if lo is not None and hi is not None and lo == hi:
        text = f"{lo:g}{unit}"
        extra = []
    elif lo is not None and hi is not None:
        text = f"от {lo:g} до {hi:g}{unit}"
        extra = [f"нижняя граница {inc(rule['include_min'])}, верхняя {inc(rule['include_max'])}"]
    elif lo is not None:
        text = (f"не менее {lo:g}{unit}" if rule["include_min"] else f"более {lo:g}{unit}")
        extra = [f"граница {inc(rule['include_min'])}"]
    else:
        text = (f"не более {hi:g}{unit}" if rule["include_max"] else f"менее {hi:g}{unit}")
        extra = [f"граница {inc(rule['include_max'])}"]
    if tol:
        extra.append(f"допуск ±{tol:g}{unit}")
    return text + (f" ({'; '.join(extra)})" if extra else "")
