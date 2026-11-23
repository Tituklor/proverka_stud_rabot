"""Разбор docx: извлекаем факты (значения параметров) и строим дерево разделов.

Значения, которые не заданы в абзаце, берутся из стиля (и его родителей),
затем из настроек документа по умолчанию. Если значение нигде не задано,
оно считается неопределённым: факт не создаётся, нарушения не будет.
"""
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH as ALIGN
from docx.oxml.ns import qn
from docx.shared import Length, Twips
from docx.text.paragraph import Paragraph

HEADING_RE = re.compile(r"^(heading|заголовок)\s*(\d)$", re.IGNORECASE)
ALIGN_NAMES = {
    ALIGN.LEFT: "по левому краю", ALIGN.CENTER: "по центру",
    ALIGN.RIGHT: "по правому краю", ALIGN.JUSTIFY: "по ширине",
}
JC_VALUES = {"both": ALIGN.JUSTIFY, "left": ALIGN.LEFT, "start": ALIGN.LEFT,
             "center": ALIGN.CENTER, "right": ALIGN.RIGHT, "end": ALIGN.RIGHT}


class NoHeadingsError(Exception):
    """В документе нет ни одного заголовка 1 уровня."""


# ---------- вспомогательные функции ----------

def normalize(text):
    """Название раздела без регистра, нумерации и знаков препинания."""
    t = text.lower().replace("ё", "е")
    t = re.sub(r"^[\d\.\s\)]+", "", t)
    t = re.sub(r"[^a-zа-я0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def classify(title, elements):
    """Определяет ключ структурного элемента по тексту заголовка."""
    norm = normalize(title)
    for el in elements:
        if norm in el["titles"]:
            return el["key"]
        if any(norm.startswith(p) for p in el.get("title_prefixes", [])):
            return el["key"]
    return "main"  # любой другой Heading 1 считаем разделом основной части


def heading_level(par):
    name = par.style.name if par.style is not None else ""
    m = HEADING_RE.match(name.strip())
    return int(m.group(2)) if m else None


def style_chain(style):
    while style is not None:
        yield style
        style = style.base_style


def read_defaults(doc):
    """Значения по умолчанию из w:docDefaults."""
    root = doc.styles.element
    d = {}
    rfonts = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts")
    if rfonts and rfonts[0].get(qn("w:ascii")):
        d["name"] = rfonts[0].get(qn("w:ascii"))
    sz = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:sz")
    if sz:
        d["size"] = int(sz[0].get(qn("w:val"))) / 2
    b = root.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:b")
    if b:
        d["bold"] = b[0].get(qn("w:val")) not in ("0", "false")
    sp = root.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:spacing")
    if sp and sp[0].get(qn("w:line")) and sp[0].get(qn("w:lineRule"), "auto") == "auto":
        d["line_spacing"] = int(sp[0].get(qn("w:line"))) / 240
    ind = root.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:ind")
    if ind and ind[0].get(qn("w:firstLine")):
        d["first_line_indent"] = Twips(int(ind[0].get(qn("w:firstLine"))))
    jc = root.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:jc")
    if jc and jc[0].get(qn("w:val")) in JC_VALUES:
        d["alignment"] = JC_VALUES[jc[0].get(qn("w:val"))]
    return d


def run_prop(run, par, name, defaults):
    """Свойство шрифта: run -> стиль абзаца (и родители) -> умолчания документа."""
    v = getattr(run.font, name)
    if v is None:
        for st in style_chain(par.style):
            v = getattr(st.font, name)
            if v is not None:
                break
    if v is None:
        v = defaults.get(name)
    if name == "size" and isinstance(v, Length):
        v = v.pt
    return v


def para_prop(par, name, defaults):
    """Свойство абзаца: абзац -> стиль (и родители) -> умолчания документа."""
    v = getattr(par.paragraph_format, name)
    if v is None:
        for st in style_chain(par.style):
            v = getattr(st.paragraph_format, name)
            if v is not None:
                break
    if v is None:
        v = defaults.get(name)
    return v


def add(facts, key, value, role, place, note=None):
    obs = {"value": value, "role": role, "place": place}
    if note:
        obs["note"] = note
    facts.setdefault(key, []).append(obs)


def iter_body(doc):
    """Верхний уровень документа: абзацы и таблицы по порядку."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "p", Paragraph(child, doc._body)
        elif child.tag == qn("w:tbl"):
            yield "tbl", None


def build_tree(headings):
    """Дерево разделов: Heading 1 -> Heading 2 -> ..."""
    root = {"level": 0, "children": []}
    stack = [root]
    for h in headings:
        node = dict(h, children=[])
        while stack[-1]["level"] >= h["level"]:
            stack.pop()
        stack[-1]["children"].append(node)
        stack.append(node)
    return root["children"]


def page_number_alignment(footer, defaults):
    """None, если в колонтитуле нет поля PAGE; иначе выравнивание строки с номером."""
    for par in footer.paragraphs:
        instr = " ".join(par._p.xpath(".//w:instrText/text() | .//w:fldSimple/@w:instr"))
        if re.search(r"\bPAGE\b", instr):
            al = para_prop(par, "alignment", defaults)
            return ALIGN_NAMES.get(al, "по левому краю")  # не задано = по левому краю
    return None


# ---------- основная функция ----------

def parse_document(path, elements):
    doc = Document(path)
    defaults = read_defaults(doc)

    # Проход 1: список абзацев, определение титульного листа и заголовков
    paras, has_title, seen_h1, n = [], False, False, 0
    for kind, par in iter_body(doc):
        if kind == "tbl":
            if not seen_h1:
                has_title = True
            continue
        n += 1
        text = par.text.strip()
        level = heading_level(par) if text else None
        if level == 1:
            seen_h1 = True
        elif text and level is None and not seen_h1:
            has_title = True
        paras.append({"idx": n, "par": par, "text": text, "level": level, "before_h1": not seen_h1})
    if not seen_h1:
        raise NoHeadingsError("В документе не найдены заголовки со стилем «Заголовок 1» (Heading 1). "
                              "Оформите заголовки разделов этим стилем и повторите проверку.")

    # Проход 2: роли абзацев и факты
    facts, headings = {}, []
    section, key = "титульный лист", None
    kw_found = referat_seen = False
    for p in paras:
        text, par, idx = p["text"], p["par"], p["idx"]
        if not text:
            continue
        if p["level"] is not None:
            role = "heading"
            if p["level"] == 1:
                key = classify(text, elements)
                section = text
                referat_seen = referat_seen or key == "abstract"
                headings.append({"level": 1, "title": text, "key": key, "paragraph": idx})
            else:
                headings.append({"level": p["level"], "title": text, "key": None, "paragraph": idx})
        elif p["before_h1"]:
            role = "title"
        elif key == "contents":
            role = "toc"
        else:
            role = "body"
        if role == "title":
            continue

        place = {"paragraph": idx, "section": section, "snippet": text[:40] + ("…" if len(text) > 40 else "")}
        runs = [r for r in par.runs if r.text.strip()]

        # шрифт: все не титульные абзацы
        for name in dict.fromkeys(run_prop(r, par, "name", defaults) for r in runs):
            if name:
                add(facts, "font_name", name, role, place)

        if role == "heading":
            bolds = [run_prop(r, par, "bold", defaults) for r in runs]
            if bolds and all(b is True for b in bolds):
                add(facts, "bold_in_heading", "полужирный", role, place)
            elif any(b is False for b in bolds):
                add(facts, "bold_in_heading", "не полужирный", role, place)
            continue
        if role == "toc":
            continue

        # основной текст
        for size in dict.fromkeys(run_prop(r, par, "size", defaults) for r in runs):
            if size:
                add(facts, "font_size_pt", round(float(size), 2), role, place)
        bolds = [run_prop(r, par, "bold", defaults) for r in runs]
        add(facts, "bold_in_body", "содержит полужирный" if any(b is True for b in bolds) else "без полужирного",
            role, place)

        ls = para_prop(par, "line_spacing", defaults)
        if isinstance(ls, float):
            add(facts, "line_spacing", round(ls, 2), role, place)
        elif ls is not None:  # точное значение в пунктах — это не «полуторный»
            add(facts, "line_spacing", f"фиксированный {ls.pt:g} пт", role, place)
        ind = para_prop(par, "first_line_indent", defaults)
        if ind is not None:
            add(facts, "first_line_indent_cm", round(ind.cm, 2), role, place)
        al = para_prop(par, "alignment", defaults)
        if al is not None:
            add(facts, "alignment", ALIGN_NAMES.get(al, str(al)), role, place)

        # ключевые слова реферата: первая строка прописными буквами с запятыми
        if (key == "abstract" and not kw_found and "," in text and text.upper() == text
                and re.search(r"[A-ZА-ЯЁ]", text)):
            count = len([w for w in text.split(",") if w.strip()])
            add(facts, "keywords_count", count, "document", place)
            kw_found = True
    if referat_seen and not kw_found:
        add(facts, "keywords_count", 0, "document", {"where": "раздел «Реферат»"},
            note="строка с перечнем ключевых слов не найдена")

    # Параметры страниц: поля и нумерация
    for i, sec in enumerate(doc.sections, 1):
        where = {"where": f"секция {i}"}
        for key_name, value in (("margin_left_mm", sec.left_margin), ("margin_right_mm", sec.right_margin),
                                ("margin_top_mm", sec.top_margin), ("margin_bottom_mm", sec.bottom_margin)):
            if value is not None:
                add(facts, key_name, round(value.mm, 1), "document", where)
        if i == 1 or not sec.footer.is_linked_to_previous:
            al = page_number_alignment(sec.footer, defaults)
            add(facts, "page_number", al or "отсутствует", "document", {"where": f"секция {i}, нижний колонтитул"})
    first = doc.sections[0]
    footer = first.first_page_footer if first.different_first_page_header_footer else first.footer
    has_num = page_number_alignment(footer, defaults) is not None
    add(facts, "title_page_number", "есть" if has_num else "отсутствует", "document", {"where": "первая страница"})

    tree = build_tree(headings)
    elements_found = [{"key": h["key"], "title": h["title"], "paragraph": h["paragraph"]}
                      for h in tree if h["level"] == 1]
    return {"facts": facts, "tree": tree,
            "structure": {"has_title": has_title, "elements": elements_found}, "paragraphs": n}
