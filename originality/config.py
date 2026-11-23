import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "threshold_percent": 25.0,   
    "semantic_threshold": 0.83,  
    "shingle_threshold": 0.5, 
    "shingle_size": 5,
    "window_sentences": 3,
    "window_step": 2, 
    "min_fragment_words": 5,
    "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
    "db_path": "data/originality.db",
    "log_path": "data/check.log",
}


def load_settings(overrides=None):
    settings = dict(DEFAULTS)
    path = ROOT / "settings.json"
    if path.exists():
        try:
            settings.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            raise ValueError(f"Не удалось прочитать settings.json: {e}")
    if overrides:
        settings.update(overrides)
    for key in ("db_path", "log_path"):
        p = Path(settings[key])
        if not p.is_absolute():
            settings[key] = str(ROOT / p)
    return settings
