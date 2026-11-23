"""Проверка курсовой: оформление (ГОСТ 7.32-2017) + антиплагиат.

Просто запустите файл (кнопка Run в PyCharm или `python main.py`):
программа спросит путь к docx-файлу и покажет меню.
"""
import json
import os
import sys

from checker import check_report
from checker.result import format_text

# Настройки, которые меняются из меню (бывшие --id, --threshold, --no-cache, --json)
opt = {"id": None, "threshold": None, "cache": True, "json": False}


def ask_path():
    """Спрашивает путь, пока не будет указан существующий файл."""
    while True:
        path = input("Путь к docx-файлу: ").strip().strip('"').strip("'")
        if not path:
            continue
        if os.path.isfile(path):
            return path
        print(f"Файл не найден: {path}")


def run_format(path):
    """Проверка оформления. Возвращает True, если оформление в порядке."""
    print("\n--- Проверка оформления (ГОСТ 7.32-2017) ---")
    res = check_report(path, use_cache=opt["cache"])
    if opt["json"]:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_text(res))
    return res["status"] == "ok" and res["verdict"] == "допущена"


def run_plagiarism(path, save=True):
    """Антиплагиат: save=True — проверить и сохранить (check), False — только добавить в базу (add)."""
    # Импорт тут, чтобы тяжёлая модель не грузилась, пока антиплагиат не нужен
    from originality import check_work, add_work, to_json, to_text_report

    print("\n--- Антиплагиат ---" if save else "\n--- Добавление в базу ---")
    if save:
        overrides = {"threshold_percent": opt["threshold"]} if opt["threshold"] is not None else None
        res = check_work(path, opt["id"], overrides)
    else:
        res = add_work(path, opt["id"])
    print(to_json(res) if opt["json"] else to_text_report(res))


def run_full(path):
    """Сначала оформление, и только если всё хорошо — антиплагиат."""
    if run_format(path):
        run_plagiarism(path)
    else:
        print("\nОформление не прошло (или проверка не выполнена) — антиплагиат не запускался.")


def set_id():
    value = input("ID работы в базе (Enter — имя файла): ").strip()
    opt["id"] = value or None


def set_threshold():
    value = input("Порог заимствований, % (Enter — из settings.json): ").strip().replace(",", ".")
    if not value:
        opt["threshold"] = None
        return
    try:
        opt["threshold"] = float(value)
    except ValueError:
        print("Нужно число, например 25. Порог не изменён.")


def toggle(key):
    opt[key] = not opt[key]


MENU = """
==================== МЕНЮ ====================
Файл: {path}

 1. Полная проверка (оформление -> антиплагиат)
 2. Только оформление
 3. Только антиплагиат (проверить и сохранить в базу)
 4. Добавить в базу без проверки
 5. Выбрать другой файл

 Настройки:
 6. ID работы: {id}
 7. Порог заимствований: {threshold}
 8. Кэш проверки оформления: {cache}
 9. Вывод в JSON: {json}

 0. Выход
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    path = ask_path()
    actions = {
        "1": run_full,
        "2": run_format,
        "3": lambda p: run_plagiarism(p, save=True),
        "4": lambda p: run_plagiarism(p, save=False),
    }
    while True:
        print(MENU.format(
            path=path,
            id=opt["id"] or "имя файла",
            threshold=f"{opt['threshold']}%" if opt["threshold"] is not None else "из settings.json",
            cache="вкл" if opt["cache"] else "выкл",
            json="вкл" if opt["json"] else "выкл",
        ))
        choice = input("Выберите пункт: ").strip()
        if choice == "0":
            break
        if choice == "5":
            path = ask_path()
            opt["id"] = None  # ID по умолчанию — имя файла, для нового файла старый ID не нужен
        elif choice == "6":
            set_id()
        elif choice == "7":
            set_threshold()
        elif choice == "8":
            toggle("cache")
        elif choice == "9":
            toggle("json")
        elif choice in actions:
            actions[choice](path)
        else:
            print("Нет такого пункта.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nВыход.")
