"""Модуль приёма запроса: файл существует, читается, это корректный docx."""
import os
import zipfile


def validate_request(path):
    """Возвращает (True, "") или (False, понятное сообщение об ошибке)."""
    if not isinstance(path, (str, os.PathLike)) or not str(path).strip():
        return False, "Путь к файлу не указан."
    path = str(path)
    if not os.path.exists(path):
        return False, f"Файл не найден: {path}"
    if not os.path.isfile(path):
        return False, "Указанный путь не является файлом."

    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return False, "Формат PDF не поддерживается: параметры оформления из него не извлекаются. Сохраните отчёт в формате DOCX."
    if ext != ".docx":
        return False, f"Формат «{ext or 'без расширения'}» не поддерживается. Допустим только DOCX."

    try:
        if os.path.getsize(path) == 0:
            return False, "Файл пустой."
        with open(path, "rb") as f:
            f.read(1)
    except OSError as e:
        return False, f"Файл не удаётся прочитать: {e}"

    # docx — это zip-архив с word/document.xml внутри
    if not zipfile.is_zipfile(path):
        return False, "Файл повреждён: он не является корректным DOCX."
    try:
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                return False, "Файл повреждён: архив DOCX содержит ошибки."
            if "word/document.xml" not in z.namelist():
                return False, "Файл повреждён: в нём нет основного содержимого документа (word/document.xml)."
    except zipfile.BadZipFile:
        return False, "Файл повреждён: архив DOCX не открывается."
    return True, ""
