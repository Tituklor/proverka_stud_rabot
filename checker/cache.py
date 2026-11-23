"""Кэш результатов. Ключ = SHA-256 файла + имя профиля + хеш файла правил."""
import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_key(path, profile, rules_path):
    text = f"{_file_hash(path)}|{profile}|{_file_hash(rules_path)}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(key):
    try:
        with open(CACHE_DIR / f"{key}.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):  # нет файла или он испорчен — считаем, что кэша нет
        return None


def save(key, result):
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
