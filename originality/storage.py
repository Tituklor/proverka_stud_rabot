"""Хранилище работ в одном файле SQLite (переживает перезапуск программы)."""
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np


class StorageError(Exception):
    pass


class Storage:
    def __init__(self, db_path, model_name):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._check_model(model_name)

    def _create_tables(self):
        with self.conn:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS works (
                id INTEGER PRIMARY KEY,
                seq INTEGER NOT NULL,           -- порядок первой загрузки (при замене версии не меняется)
                work_id TEXT UNIQUE NOT NULL,   -- идентификатор работы (студент + название)
                uploaded_at TEXT NOT NULL,
                status TEXT,                    -- admitted / returned / added
                borrowed_percent REAL,
                text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fragments (
                id INTEGER PRIMARY KEY,
                work_pk INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
                idx INTEGER NOT NULL,
                text TEXT NOT NULL,
                vector BLOB NOT NULL);          -- float32, байты numpy-массива
            CREATE TABLE IF NOT EXISTS shingles (
                hash INTEGER NOT NULL,
                fragment_id INTEGER NOT NULL REFERENCES fragments(id) ON DELETE CASCADE,
                PRIMARY KEY (hash, fragment_id)) WITHOUT ROWID;  -- быстрый поиск по hash
            """)

    def _check_model(self, model_name):
        """Векторы разных моделей несравнимы, поэтому запоминаем модель базы."""
        row = self.conn.execute("SELECT value FROM meta WHERE key='model'").fetchone()
        if row is None:
            with self.conn:
                self.conn.execute("INSERT INTO meta VALUES ('model', ?)", (model_name,))
        elif row[0] != model_name:
            raise StorageError(
                f"База создана с моделью «{row[0]}», а сейчас используется «{model_name}». "
                f"Векторы несовместимы: удалите файл базы или верните прежнюю модель.")

    def seq_for(self, work_id):
        """Порядковый номер работы: (номер, уже_была_в_базе).

        Новая работа получает следующий номер. При повторной загрузке сохраняется
        старый номер, поэтому сравнивать её нужно только с работами, загруженными
        РАНЬШЕ первой версии, а не с теми, кто мог списать у неё позднее.
        """
        row = self.conn.execute("SELECT seq FROM works WHERE work_id=?", (work_id,)).fetchone()
        if row:
            return row[0], True
        last = self.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM works").fetchone()[0]
        return last + 1, False

    def save_work(self, work_id, text, status, percent, fragments, vectors, shingle_sets):
        """Сохраняет работу целиком. Работа с тем же work_id заменяется новой версией."""
        seq, _ = self.seq_for(work_id)
        with self.conn:  # одна транзакция: либо сохранилось всё, либо ничего
            self.conn.execute("DELETE FROM works WHERE work_id=?", (work_id,))  # каскадом удалит фрагменты
            cur = self.conn.execute(
                "INSERT INTO works (seq, work_id, uploaded_at, status, borrowed_percent, text) VALUES (?,?,?,?,?,?)",
                (seq, work_id, datetime.now().isoformat(timespec="seconds"), status, percent, text))
            work_pk = cur.lastrowid
            for i, frag in enumerate(fragments):
                cur = self.conn.execute(
                    "INSERT INTO fragments (work_pk, idx, text, vector) VALUES (?,?,?,?)",
                    (work_pk, i, frag, np.asarray(vectors[i], dtype=np.float32).tobytes()))
                self.conn.executemany("INSERT INTO shingles VALUES (?,?)",
                                      [(h, cur.lastrowid) for h in shingle_sets[i]])
        return work_pk

    def load_vectors(self, before_seq):
        """Фрагменты работ, загруженных раньше номера before_seq: (матрица, описания)."""
        rows = self.conn.execute(
            "SELECT f.id, w.work_id, f.text, f.vector FROM fragments f "
            "JOIN works w ON w.id = f.work_pk WHERE w.seq < ?",
            (before_seq,)).fetchall()
        if not rows:
            return np.zeros((0, 0), dtype=np.float32), []
        matrix = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
        meta = [{"fragment_id": r[0], "work_id": r[1], "text": r[2]} for r in rows]
        return matrix, meta

    def shingle_overlap(self, hashes, before_seq):
        """Для набора хешей возвращает {id фрагмента: сколько шинглов совпало}."""
        hashes = list(hashes)
        counts = {}
        for start in range(0, len(hashes), 500):
            chunk = hashes[start:start + 500]
            marks = ",".join("?" * len(chunk))
            rows = self.conn.execute(
                f"SELECT s.fragment_id, COUNT(*) FROM shingles s "
                f"JOIN fragments f ON f.id = s.fragment_id "
                f"JOIN works w ON w.id = f.work_pk "
                f"WHERE s.hash IN ({marks}) AND w.seq < ? GROUP BY s.fragment_id",
                chunk + [before_seq]).fetchall()
            for fragment_id, n in rows:
                counts[fragment_id] = counts.get(fragment_id, 0) + n
        return counts

    def close(self):
        self.conn.close()
