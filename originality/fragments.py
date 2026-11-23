"""Деление текста на предложения, фрагменты-окна и шинглы."""
import re
import zlib

_SENT_SPLIT = re.compile(
    r'(?:(?<=[.!?…])|(?<=[.!?…][»"”]))\s+(?=[«"“A-ZА-ЯЁ0-9])')


def words(text):
    """Слова в нижнем регистре (ё заменяем на е). Работает для русского и английского."""
    return re.findall(r"\w+", text.lower().replace("ё", "е"))


def split_sentences(text):
    sentences = []
    for line in text.split("\n"):
        for part in _SENT_SPLIT.split(line):
            part = part.strip()
            if part and re.search(r"\w", part):
                sentences.append(part)
    return sentences


def make_fragments(text, window=3, step=2, min_words=5):
    """Окна по `window` предложений с шагом `step`. Короткие окна отбрасываем."""
    sentences = split_sentences(text)
    fragments = []
    start = 0
    while start < len(sentences):
        fragment = " ".join(sentences[start:start + window])
        if len(words(fragment)) >= min_words:
            fragments.append(fragment)
        if start + window >= len(sentences):
            break
        start += step
    return fragments


def shingles(text, size=5):
    ws = words(text)
    return {zlib.crc32(" ".join(ws[i:i + size]).encode("utf-8"))
            for i in range(len(ws) - size + 1)}
