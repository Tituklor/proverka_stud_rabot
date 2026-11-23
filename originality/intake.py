"""Приём запроса: проверяем файл до того, как его читать."""
from pathlib import Path

ALLOWED_EXTENSIONS = {".docx"}


def validate_file(path):
    """Возвращает None, если файл годится, иначе текст ошибки."""
    if path is None or str(path).strip() == "":
        return "Не указан путь к файлу."
    p = Path(str(path))
    if not p.exists():
        return f"Файл не найден: {p}"
    if not p.is_file():
        return f"Указанный путь не является файлом: {p}"
    ext = p.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return (f"Формат «{ext or 'без расширения'}» не поддерживается. "
                f"Допустимы только файлы: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")
    try:
        if p.stat().st_size == 0:
            return "Файл пуст (0 байт)."
        with open(p, "rb") as f:
            f.read(1)
    except OSError as e:
        return f"Файл нельзя прочитать: {e}"
    return None