import json


def reason_for(match, settings):
    if match["kind"] == "exact":
        return (f"Дословное совпадение: {match['shingle_overlap']:.0%} последовательностей из "
                f"{settings['shingle_size']} слов есть в работе «{match['source_work_id']}» "
                f"(порог {settings['shingle_threshold']:.0%}).")
    return (f"Смысловое совпадение (возможно, перефразирование): косинусное сходство "
            f"{match['similarity']:.2f} при пороге {settings['semantic_threshold']:.2f}.")


def add_reasons(match_list, settings):
    for m in match_list:
        m["reason"] = reason_for(m, settings)


def to_json(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


def to_text_report(result):
    lines = [f"Работа: {result['work_id']}    Файл: {result['file']}"]
    if result["status"] == "error":
        lines.append(f"ОШИБКА: {result['error']}")
        lines.append("Вердикт не вынесен, работа не сохранена.")
        return "\n".join(lines)

    if result["mode"] == "add":
        lines.append("Работа добавлена в базу без проверки.")
    else:
        lines.append(f"Вердикт: {result['verdict']}")
        lines.append(f"Заимствований: {result['borrowed_percent']:.1f}% "
                     f"(порог {result['threshold_percent']:.1f}%, граница включается в допуск)")
        lines.append(f"Фрагментов: всего {result['fragments_total']}, совпало {result['fragments_matched']}")
    if result["citations_excluded"]:
        lines.append(f"Исключено правомерных цитат (в кавычках со ссылкой): {result['citations_excluded']}.")
    if result["bibliography_excluded"]:
        lines.append("Раздел «Список литературы» исключён из проверки.")
    excluded_sections = result.get("diagnostics", {}).get("excluded_sections") or []
    if excluded_sections:
        lines.append(f"Исключены стандартные разделы ГОСТ: {', '.join(excluded_sections)}.")
    for w in result["warnings"]:
        lines.append(f"ВНИМАНИЕ: {w}")

    for n, m in enumerate(result["matches"], 1):
        lines += ["", f"--- Совпадение {n} ---",
                  f"Фрагмент: {m['fragment']}",
                  f"Источник: работа «{m['source_work_id']}»",
                  f"Фрагмент источника: {m['source_fragment']}",
                  f"Сходство: {m['similarity']:.2f}",
                  f"Причина: {m['reason']}"]
    for q in result["excluded_citations"]:
        shown = q if len(q) <= 200 else q[:200] + "…"
        lines += ["", f"--- Не проверялось (правомерная цитата) ---", shown]
    
    return "\n".join(lines)
