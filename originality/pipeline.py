"""Главные функции подсистемы: собирают все шаги проверки по порядку."""
from datetime import datetime
from pathlib import Path

from .config import load_settings
from .log import get_logger
from .intake import validate_file
from .extractor import extract_document, ExtractError
from .fragments import make_fragments, shingles
from .embedder import Embedder
from .storage import Storage, StorageError
from .comparer import find_matches
from . import rules, verdict, explain


_embedders = {}


def _get_embedder(model_name):
    if model_name not in _embedders:
        _embedders[model_name] = Embedder(model_name)
    return _embedders[model_name]


class CheckError(Exception):
    """Ожидаемая ошибка проверки; сообщение показываем пользователю."""


def check_work(path, work_id=None, settings=None, embedder=None):
    return _run(path, work_id, settings, embedder, compare=True)


def add_work(path, work_id=None, settings=None, embedder=None):
    """Сохраняет работу в базу без проверки (для заполнения базы сравнения)."""
    return _run(path, work_id, settings, embedder, compare=False)


def _new_result(path, work_id, cfg, compare):
    return {
        "status": "ok",                       # ok / error
        "mode": "check" if compare else "add",
        "work_id": work_id,
        "file": str(path),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "verdict": None,
        "admitted": None,
        "borrowed_percent": 0.0,
        "threshold_percent": cfg["threshold_percent"],
        "comparison_done": False,
        "fragments_total": 0,
        "fragments_matched": 0,
        "citations_excluded": 0,
        "bibliography_excluded": False,
        "matches": [], 
        "excluded_citations": [],
        "warnings": [],
        "error": None,
        "saved": False,
        "diagnostics": {},
    }


def _run(path, work_id, overrides, embedder, compare):
    try:
        cfg = load_settings(overrides)
    except ValueError as e:
        return _error_result(path, work_id, {"threshold_percent": None}, compare, str(e))
    log = get_logger(cfg["log_path"])
    work_id = work_id or Path(str(path)).stem
    result = _new_result(path, work_id, cfg, compare)
    log.info(f"Начало: {work_id} ({path}), режим={result['mode']}")

    try:
        _process(path, work_id, cfg, embedder, compare, result, log)
    except (CheckError, ExtractError, StorageError) as e:
        log.warning(f"{work_id}: {e}")
        return _error_result(path, work_id, cfg, compare, str(e))
    except Exception as e:
        log.exception(f"{work_id}: непредвиденная ошибка")
        return _error_result(path, work_id, cfg, compare, f"Непредвиденная ошибка: {type(e).__name__}: {e}")

    log.info(f"Конец: {work_id}, вердикт={result['verdict']}, заимствований={result['borrowed_percent']:.1f}%")
    return result


def _error_result(path, work_id, cfg, compare, message):
    result = _new_result(path, work_id or Path(str(path)).stem, cfg, compare)
    result["status"] = "error"
    result["error"] = message
    return result


def _process(path, work_id, cfg, embedder, compare, result, log):
    error = validate_file(path)
    if error:
        raise CheckError(error)
    extracted = extract_document(path)
    text = extracted["text"]
    log.info(f"{work_id}: извлечено {len(text)} символов")

    main_text, had_bibliography_in_text = rules.cut_bibliography(text)
    main_text, quotes = rules.remove_citations(main_text)
    result["bibliography_excluded"] = bool(extracted["bibliography_excluded"] or had_bibliography_in_text)
    result["excluded_citations"] = quotes
    result["citations_excluded"] = len(quotes)
    result["diagnostics"]["excluded_sections"] = extracted["excluded_sections"]
    result["diagnostics"]["title_page_excluded"] = extracted["title_page_excluded"]

    fragments = make_fragments(main_text, cfg["window_sentences"], cfg["window_step"],
                               cfg["min_fragment_words"])
    if not fragments:
        raise CheckError(f"Текст слишком короткий: не получилось ни одного фрагмента "
                         f"(нужно хотя бы {cfg['min_fragment_words']} слов).")
    shingle_sets = [shingles(f, cfg["shingle_size"]) for f in fragments]
    embedder = embedder or _get_embedder(cfg["model_name"])
    try:
        vectors = embedder.encode(fragments)
    except Exception as e:
        log.exception(f"{work_id}: ошибка модели")
        raise CheckError(f"Не удалось вычислить векторы (модель не загрузилась?): {e}")
    log.info(f"{work_id}: фрагментов {len(fragments)}")

    storage = Storage(cfg["db_path"], embedder.name)
    try:
        before_seq, existed = storage.seq_for(work_id)
        if existed:
            result["warnings"].append(
                f"Работа «{work_id}» уже была в базе: старая версия заменена новой. "
                f"Сравнение идёт только с работами, загруженными раньше первой версии.")

        status = "added"
        if compare:
            found, best, has_reference = find_matches(vectors, shingle_sets, storage, before_seq, cfg)
            result["comparison_done"] = has_reference
            result["diagnostics"]["best_similarity_per_fragment"] = best
            if not has_reference:
                result["warnings"].append(
                    "В базе нет ранее загруженных работ: сравнение не проводилось, 0% не означает оригинальность.")
            log.info(f"{work_id}: совпавших фрагментов {len(found)}")

            info = rules.calc_borrowing(fragments, found)
            v = verdict.make_verdict(info, cfg["threshold_percent"])
            result["matches"] = [dict(found[i], fragment=fragments[i], fragment_index=i)
                                 for i in info["matched_idx"]]
            explain.add_reasons(result["matches"], cfg)
            result.update(verdict=v["verdict"], admitted=v["admitted"],
                          borrowed_percent=round(info["percent"], 2),
                          fragments_total=info["total"], fragments_matched=info["matched"])
            status = "admitted" if v["admitted"] else "returned"
        else:
            result["fragments_total"] = len(fragments)
            result["warnings"].append("Режим добавления: проверка не выполнялась, вердикта нет.")

        storage.save_work(work_id, text, status, result["borrowed_percent"],
                          fragments, vectors, shingle_sets)
        result["saved"] = True
    finally:
        storage.close()
