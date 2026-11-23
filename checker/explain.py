"""Объяснение нарушения: цепочка «факт -> правило -> вывод»."""


def place_text(p):
    """Место нарушения в читаемом виде."""
    if "note" in p:
        return p["note"]
    if "where" in p:
        s = p["where"]
    else:
        s = f"абзац {p['paragraph']}"
        if p.get("section"):
            s += f", раздел «{p['section']}»"
        if p.get("snippet"):
            s += f": «{p['snippet']}»"
    if "value" in p:
        s += f" — {p['value']}"
    return s


def explain(v, rule):
    """Возвращает список из трёх шагов рассуждения."""
    fact = v.pop("fact_text", None)
    if not fact:
        fact = (f"из документа извлечено значений параметра: {v['checked']}; "
                f"не соответствуют правилу: {v['count']}. Найдено: {v['actual']}. "
                f"Первое место: {place_text(v['places'][0])}.")
    concl = v.pop("conclusion", None)
    if not concl:
        concl = (f"найденное значение ({v['actual']}) не удовлетворяет требованию ({v['expected']}), "
                 f"поэтому зафиксировано нарушение.")
    rule_s = f"правило {rule['id']} «{rule['name']}» требует: {v['expected']}. Источник: {rule.get('source', 'не указан')}."
    return [f"1. Факт: {fact}", f"2. Правило: {rule_s}", f"3. Вывод: {concl}"]
