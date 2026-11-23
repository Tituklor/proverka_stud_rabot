"""Правила: список литературы, правомерное цитирование, процент заимствований."""
import re

_BIBLIOGRAPHY_HEADING = re.compile(
    r"^\s*(?:\d+[.)]?\s*)?(?:"
    r"список\s+(?:использованн\w+\s+)?(?:литературы|источников)"
    r"|библиографический\s+список|литература|references"
    r")\s*[:.]?\s*$", re.IGNORECASE | re.MULTILINE)

_CITATION = re.compile(
    r'(?:«[^»]*»|"[^"]*"|“[^”]*”)\s*\.?\s*'
    r'(?:\[\d+[^\]]{0,15}\]|\([^()]{1,60}\d{4}[^()]{0,20}\))')


def cut_bibliography(text):
    """Отрезает раздел литературы. Возвращает (основной текст, был ли раздел).

    Берём ПОСЛЕДНИЙ подходящий заголовок: так оглавление, где слова
    «Список литературы» встречаются раньше, не отрежет всю работу.
    """
    found = list(_BIBLIOGRAPHY_HEADING.finditer(text))
    if not found:
        return text, False
    return text[:found[-1].start()].rstrip(), True


def remove_citations(text):
    """Вырезает правомерные цитаты ДО разбиения на фрагменты.

    Так цитата не попадает ни в числитель, ни в знаменатель процента, и
    окна строятся только из собственного текста автора (нет «хвостов» цитат).
    Возвращает (текст без цитат, список вырезанных цитат).
    Ограничение: ссылка должна стоять после цитаты, а не перед ней.
    """
    removed = [m.group(0) for m in _CITATION.finditer(text)]
    cleaned = _CITATION.sub(" ", text)
    cleaned = re.sub(r"[^\S\n]+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[^\S\n]{2,}", " ", cleaned)
    cleaned = re.sub(r"(?<!\.)\.\.(?!\.)", ".", cleaned)
    return cleaned, removed


def calc_borrowing(fragments, matches):
    """Процент заимствований = совпавшие фрагменты / все фрагменты * 100."""
    matched = sorted(matches)
    total = len(fragments)
    return {
        "total": total,
        "matched": len(matched),
        "matched_idx": matched,
        "percent": 100.0 * len(matched) / total if total else 0.0,
    }


def is_within_threshold(matched, total, threshold_percent):
    """ПРАВИЛО ГРАНИЦЫ: если процент заимствований РОВНО равен порогу,
    работа допускается (условие «не превышает» => процент <= порога).
    Сравниваем без деления (matched*100 <= порог*total), чтобы исключить
    ошибки округления дробных чисел на самой границе.
    """
    return matched * 100 <= threshold_percent * total
