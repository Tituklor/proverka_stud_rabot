"""Подсистема проверки оформления. Единая точка входа — check_report."""
import os

from . import cache
from .explain import explain
from .knowledge import KnowledgeError, load_knowledge
from .logger import get_logger
from .parser import NoHeadingsError, parse_document
from .request import validate_request
from .result import build_result, error_result
from .validator import run_checks

__all__ = ["check_report"]


def check_report(path, profile="gost_7_32", rules_dir=None, use_cache=True):
    """Проверяет docx-отчёт. Возвращает словарь:
    status ('ok' / 'error'), verdict ('допущена' / 'на доработку' / None),
    violations (список нарушений с объяснениями), message, profile, file, from_cache.
    """
    log = get_logger()
    name = os.path.basename(str(path)) if path else None
    log.info("Запрос: файл=%s, профиль=%s", path, profile)

    ok, msg = validate_request(path)
    if not ok:
        log.warning("Запрос отклонён: %s", msg)
        return error_result("file", msg, profile, name)

    try:
        kb = load_knowledge(profile, rules_dir)
    except KnowledgeError as e:
        log.error("База знаний: %s", e)
        return error_result(e.kind, str(e), profile, name)

    key = None
    if use_cache:
        key = cache.make_key(path, profile, kb.path)
        cached = cache.load(key)
        if cached:
            log.info("Результат взят из кэша (%s)", key[:12])
            cached["from_cache"] = True
            cached["file"] = name
            return cached

    try:
        parsed = parse_document(path, kb.structure_elements)
    except NoHeadingsError as e:
        log.warning("Нет заголовков: %s", e)
        return error_result("no_headings", str(e), profile, name)
    except Exception as e:  # python-docx может упасть на нестандартном xml
        log.exception("Ошибка разбора документа")
        return error_result("parse", f"Не удалось разобрать документ как DOCX: {e}", profile, name)
    log.info("Разбор: абзацев=%d, разделов верхнего уровня=%d, видов фактов=%d",
             parsed["paragraphs"], len(parsed["structure"]["elements"]), len(parsed["facts"]))

    try:
        violations = run_checks(parsed, kb)
    except Exception as e:
        log.exception("Ошибка проверки")
        return error_result("internal", f"Внутренняя ошибка проверки: {e}", profile, name)
    for v in violations:
        v["explanation"] = explain(v, kb.rule(v["rule_id"]))
        log.info("Нарушение %s: мест=%d", v["rule_id"], v["count"])

    result = build_result(violations, profile, name)
    log.info("Вердикт: %s", result["verdict"])
    if use_cache:
        cache.save(key, result)
    return result
