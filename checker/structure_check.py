"""Часть 2: проверка структуры. S01 (отсутствующие разделы) и S02 (порядок) независимы."""
from .result import make_violation


def check_structure(structure, kb):
    present = []
    if structure["has_title"]:
        present.append({"key": "title", "title": "Титульный лист", "paragraph": None})
    present += structure["elements"]

    violations = []
    for rule in kb.structure_rules:
        if rule["condition"] == "required_present":
            v = _missing(rule, present, kb)
        else:
            v = _order(rule, present, kb)
        if v:
            violations.append(v)
    return violations


def _missing(rule, present, kb):
    keys = {e["key"] for e in present}
    required = [e for e in kb.structure_elements if e["required"]]
    missing = [e["name"] for e in required if e["key"] not in keys]
    if not missing:
        return None
    found = ", ".join(e["title"] for e in present) or "ничего"
    return make_violation(
        rule,
        expected="обязательные разделы: " + ", ".join(e["name"] for e in required),
        actual="отсутствуют: " + ", ".join(missing),
        places=[{"note": f"отсутствует раздел «{n}»"} for n in missing],
        count=len(missing), checked=len(required),
        fact_text=f"в документе найдены разделы (в порядке следования): {found}. Среди них нет: {', '.join(missing)}.",
        conclusion="обязательный раздел отсутствует, поэтому зафиксировано нарушение. "
                   "Порядок имеющихся разделов проверяется отдельно (S02).")


def _order(rule, present, kb):
    rank = {e["key"]: e["order"] for e in kb.structure_elements}
    seq = [e for e in present if e["key"] in rank]
    inversions, seen = [], set()
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            a, b = seq[i], seq[j]
            if rank[a["key"]] > rank[b["key"]] and (a["key"], b["key"]) not in seen:
                seen.add((a["key"], b["key"]))  # одна и та же пара типов — одно замечание
                where = f" (абзац {b['paragraph']})" if b["paragraph"] else ""
                inversions.append({"note": f"«{b['title']}»{where} стоит после «{a['title']}», "
                                           f"хотя по ГОСТ должен идти раньше"})
    if not inversions:
        return None
    canonical = " → ".join(e["name"] for e in kb.structure_elements)
    return make_violation(
        rule,
        expected="порядок: " + canonical,
        actual=f"пар разделов в неверном порядке: {len(inversions)}",
        places=inversions, count=len(inversions), checked=len(seq),
        fact_text="порядок найденных разделов в документе: " + " → ".join(e["title"] for e in seq) + ".",
        conclusion="порядок разделов отличается от установленного ГОСТом (проверялись только имеющиеся разделы), "
                   "поэтому зафиксировано нарушение.")
