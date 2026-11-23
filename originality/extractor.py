"""Извлечение текста из .docx и удаление стандартных повторяющихся разделов ГОСТ."""
import re
from pathlib import Path


class ExtractError(Exception):
    """Ошибка чтения файла; текст сообщения показываем пользователю."""


EXCLUDED_SECTION_HEADERS = {
    "РЕФЕРАТ",
    "СОДЕРЖАНИЕ",
    "ОГЛАВЛЕНИЕ",
    "ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ",
    "ПЕРЕЧЕНЬ СОКРАЩЕНИЙ И ОБОЗНАЧЕНИЙ",
    "ПЕРЕЧЕНЬ СОКРАЩЕНИЙ, УСЛОВНЫХ ОБОЗНАЧЕНИЙ, СИМВОЛОВ, ЕДИНИЦ И ТЕРМИНОВ",
}

STOP_SECTION_HEADERS = {
    "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
    "СПИСОК ЛИТЕРАТУРЫ",
    "БИБЛИОГРАФИЧЕСКИЙ СПИСОК",
    "ЛИТЕРАТУРА",
    "REFERENCES",
}

BODY_START_HEADERS = {
    "РЕФЕРАТ",
    "СОДЕРЖАНИЕ",
    "ОГЛАВЛЕНИЕ",
    "ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ",
    "ПЕРЕЧЕНЬ СОКРАЩЕНИЙ И ОБОЗНАЧЕНИЙ",
    "ВВЕДЕНИЕ",
}

_NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S+")
_UPPER_HEADING_RE = re.compile(r"^[А-ЯЁA-Z0-9 «»\-—,:;()./]+$")
# Строки оглавления: «Название раздела ... 4», «Название\t7», «Название | 12»
_TOC_LINE_RE = re.compile(r"^.+?(?:\.{2,}|\s*\|\s*|\s{2,}|\t)\s*\d{1,3}\s*$")


def _normalize_heading(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line.strip())
    # На случай заголовка вида «СОДЕРЖАНИЕ 3» или «СОДЕРЖАНИЕ\t3»
    cleaned = re.sub(r"^(СОДЕРЖАНИЕ|ОГЛАВЛЕНИЕ|РЕФЕРАТ)(?:\s+\d{1,3})?$", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip(".:;")
    return cleaned.upper()


def _is_toc_entry_line(line: str) -> bool:
    """Проверяет, похожа ли строка на пункт оглавления с номером страницы."""
    stripped = line.strip()
    if not stripped:
        return False
    if _TOC_LINE_RE.match(stripped):
        return True
    # Строка вида «1.2 Исходные данные об альтернативах 7»
    if re.match(r"^\d+(?:\.\d+)*\s+[А-ЯЁA-Zа-яёa-z«»\"\-—\s]+\s+\d{1,3}$", stripped):
        return True
    return False


def _is_major_heading(line: str) -> bool:
    norm = _normalize_heading(line)
    if not norm:
        return False
    if norm in EXCLUDED_SECTION_HEADERS or norm in STOP_SECTION_HEADERS or norm in BODY_START_HEADERS:
        return True
    if _NUMBERED_HEADING_RE.match(line.strip()):
        return True
    if (
        4 <= len(norm) <= 120
        and line.strip() == line.strip().upper()
        and _UPPER_HEADING_RE.match(line.strip())
        and not line.strip().endswith((".", ","))
    ):
        return True
    return False


def _iter_docx_blocks(doc):
    """Итерирует абзацы и строки таблиц в порядке появления в документе."""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            txt = Paragraph(child, doc).text.strip()
            if txt:
                yield txt
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                dedup_cells = []
                for c in cells:
                    if not dedup_cells or dedup_cells[-1] != c:
                        dedup_cells.append(c)
                if dedup_cells:
                    yield " | ".join(dedup_cells)


def _strip_gost_boilerplate(lines: list[str]) -> tuple[str, dict]:
    """Удаляет титульный лист, повторяющиеся разделы (включая содержание) и список источников."""
    meta = {
        "title_page_excluded": False,
        "excluded_sections": [],
        "bibliography_excluded": False,
    }
    if not lines:
        return "", meta

    start_idx = 0
    for idx, line in enumerate(lines):
        norm = _normalize_heading(line)
        if (
            norm in BODY_START_HEADERS
            or norm in EXCLUDED_SECTION_HEADERS
            or _NUMBERED_HEADING_RE.match(line.strip())
        ):
            start_idx = idx
            break

    if start_idx > 0:
        meta["title_page_excluded"] = True

    candidate_lines = lines[start_idx:]
    filtered: list[str] = []
    skipping_excluded_section = False
    in_toc_block = False

    for line in candidate_lines:
        norm = _normalize_heading(line)

        if norm in STOP_SECTION_HEADERS:
            meta["bibliography_excluded"] = True
            break

        if norm in {"СОДЕРЖАНИЕ", "ОГЛАВЛЕНИЕ"}:
            in_toc_block = True
            skipping_excluded_section = True
            if norm not in meta["excluded_sections"]:
                meta["excluded_sections"].append(norm)
            continue

        # Пока мы внутри блока содержания, пропускаем заголовок, строки оглавления
        # и всё до начала следующего крупного раздела (например, «ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ» или «ВВЕДЕНИЕ»)
        if in_toc_block:
            if _is_toc_entry_line(line):
                continue
            if norm in EXCLUDED_SECTION_HEADERS or norm in BODY_START_HEADERS or norm in STOP_SECTION_HEADERS:
                in_toc_block = False
            elif _is_major_heading(line) and not _NUMBERED_HEADING_RE.match(line.strip()):
                in_toc_block = False
            else:
                continue

        if _is_major_heading(line):
            if norm in EXCLUDED_SECTION_HEADERS:
                skipping_excluded_section = True
                if norm not in meta["excluded_sections"]:
                    meta["excluded_sections"].append(norm)
                continue
            else:
                skipping_excluded_section = False

        if not skipping_excluded_section:
            filtered.append(line)

    return "\n".join(filtered), meta


def _read_docx(path):
    from docx import Document

    doc = Document(str(path))
    lines = list(_iter_docx_blocks(doc))
    return "\n".join(lines), {"blocks": len(lines)}


def clean_text(raw):
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    for ch in ("\xa0", "\u2009", "\u202f"):
        text = text.replace(ch, " ")
    for ch in ("\u200b", "\ufeff", "\xad", "\u200c", "\u200d"):
        text = text.replace(ch, "")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def extract_document(path):
    ext = Path(str(path)).suffix.lower()
    if ext != ".docx":
        raise ExtractError(f"Формат «{ext or 'без расширения'}» не поддерживается. Допустимы только файлы .docx.")
    try:
        raw, meta = _read_docx(path)
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError(
            f"Не удалось прочитать файл {ext}: он повреждён или имеет неверный формат ({type(e).__name__})."
        )

    cleaned_raw = clean_text(raw)
    stripped_text, gost_meta = _strip_gost_boilerplate(cleaned_raw.split("\n") if cleaned_raw else [])
    text = clean_text(stripped_text)

    if not text:
        raise ExtractError("В файле не найден содержательный текст после исключения служебных разделов.")

    return {
        "text": text,
        "bibliography_excluded": gost_meta["bibliography_excluded"],
        "excluded_sections": gost_meta["excluded_sections"],
        "title_page_excluded": gost_meta["title_page_excluded"],
        "raw_meta": meta,
    }


def extract_text(path):
    return extract_document(path)["text"]