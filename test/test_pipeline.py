"""Тесты части «Конвейер и отчёты»: pipeline, verdict, explain, log."""
import json
import os
import shutil
import tempfile
import unittest

from docx import Document

from originality import check_work, add_work, to_json, to_text_report
from originality.embedder import StubEmbedder
from originality import verdict
from originality.log import get_logger

BASE = ("Нейронные сети применяются для распознавания образов в медицине. "
        "Обучение модели требует большого объёма размеченных данных. "
        "Качество классификации зависит от архитектуры и параметров сети. "
        "Регуляризация помогает избежать переобучения на малых выборках. "
        "Сверточные слои выделяют локальные признаки изображения. "
        "Полносвязные слои объединяют признаки для итогового решения.")
OTHER = ("Квантовые вычисления используют суперпозицию состояний кубитов. "
         "Алгоритм Шора позволяет разлагать числа на простые множители. "
         "Декогеренция остаётся главным препятствием для масштабирования. "
         "Коррекция ошибок требует большого числа физических кубитов. "
         "Топологические кубиты считаются более устойчивыми к шуму. "
         "Первые коммерческие системы насчитывают десятки кубитов.")


def make_docx(path, text):
    d = Document()
    for p in text.split("\n"):
        d.add_paragraph(p)
    d.save(path)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.s = {"db_path": os.path.join(self.tmp, "t.db"),
                  "log_path": os.path.join(self.tmp, "t.log")}
        self.emb = StubEmbedder()

    def tearDown(self):
        import logging
        lg = logging.getLogger("originality")
        for h in list(lg.handlers):
            h.close(); lg.removeHandler(h)
        import originality.log as L
        L._current_path = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def f(self, name, text):
        p = os.path.join(self.tmp, name)
        make_docx(p, text)
        return p

    def check(self, path, wid=None, **extra):
        return check_work(path, wid, {**self.s, **extra}, self.emb)

    def add(self, path, wid=None):
        return add_work(path, wid, self.s, self.emb)


class TestVerdict(unittest.TestCase):
    def test_below_threshold_admitted(self):
        self.assertTrue(verdict.make_verdict({"matched": 1, "total": 10}, 25.0)["admitted"])

    def test_boundary_included(self):
        self.assertTrue(verdict.make_verdict({"matched": 1, "total": 4}, 25.0)["admitted"])

    def test_above_threshold_returned(self):
        v = verdict.make_verdict({"matched": 2, "total": 4}, 25.0)
        self.assertFalse(v["admitted"])
        self.assertEqual(v["verdict"], verdict.RETURNED)

    def test_zero_matches(self):
        self.assertTrue(verdict.make_verdict({"matched": 0, "total": 5}, 0.0)["admitted"])


class TestPipeline(Base):
    def test_original_work_admitted(self):
        self.add(self.f("a.docx", BASE), "A")
        r = self.check(self.f("b.docx", OTHER), "B")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["admitted"])
        self.assertEqual(r["fragments_matched"], 0)
        self.assertTrue(r["comparison_done"])

    def test_plagiarism_returned(self):
        self.add(self.f("a.docx", BASE), "A")
        r = self.check(self.f("b.docx", BASE), "B")
        self.assertEqual(r["status"], "ok")
        self.assertFalse(r["admitted"])
        self.assertEqual(r["verdict"], verdict.RETURNED)
        self.assertGreater(r["borrowed_percent"], 25.0)
        self.assertEqual(r["matches"][0]["source_work_id"], "A")
        self.assertIn("reason", r["matches"][0])

    def test_empty_base_warning(self):
        r = self.check(self.f("a.docx", BASE), "A")
        self.assertFalse(r["comparison_done"])
        self.assertTrue(any("нет ранее загруженных" in w for w in r["warnings"]))

    def test_add_mode_no_verdict(self):
        r = self.add(self.f("a.docx", BASE), "A")
        self.assertEqual(r["mode"], "add")
        self.assertIsNone(r["verdict"])
        self.assertTrue(r["saved"])

    def test_reupload_replaces_and_warns(self):
        self.add(self.f("a.docx", BASE), "A")
        r = self.check(self.f("a2.docx", OTHER), "A")
        self.assertTrue(any("уже была в базе" in w for w in r["warnings"]))

    def test_quote_excluded(self):
        self.add(self.f("a.docx", BASE), "A")
        quoted = OTHER + ' «Нейронные сети применяются для распознавания образов в медицине» [1].'
        r = self.check(self.f("q.docx", quoted), "Q")
        self.assertEqual(r["citations_excluded"], 1)

    def test_custom_threshold(self):
        self.add(self.f("a.docx", BASE), "A")
        r = self.check(self.f("b.docx", BASE), "B", threshold_percent=100.0)
        self.assertTrue(r["admitted"])


class TestErrors(Base):
    def test_missing_file(self):
        r = self.check(os.path.join(self.tmp, "nope.docx"), "X")
        self.assertEqual(r["status"], "error")
        self.assertIsNone(r["verdict"])
        self.assertIn("не найден", r["error"])

    def test_wrong_extension(self):
        p = os.path.join(self.tmp, "a.txt")
        with open(p, "w") as fh:
            fh.write("text")
        self.assertIn("не поддерживается", self.check(p)["error"])

    def test_corrupted_docx(self):
        p = os.path.join(self.tmp, "bad.docx")
        with open(p, "wb") as fh:
            fh.write(b"not a zip at all")
        r = self.check(p)
        self.assertEqual(r["status"], "error")
        self.assertIsNone(r["verdict"])

    def test_too_short_text(self):
        r = self.check(self.f("s.docx", "Мало слов."), "S")
        self.assertEqual(r["status"], "error")
        self.assertIn("слишком короткий", r["error"])

    def test_model_failure(self):
        class Bad:
            name = "bad"
            def encode(self, t): raise RuntimeError("нет модели")
        r = check_work(self.f("a.docx", BASE), "A", self.s, Bad())
        self.assertEqual(r["status"], "error")
        self.assertIn("векторы", r["error"])

    def test_model_mismatch(self):
        self.add(self.f("a.docx", BASE), "A")
        class Other(StubEmbedder):
            name = "other-model"
        r = check_work(self.f("b.docx", BASE), "B", self.s, Other())
        self.assertEqual(r["status"], "error")
        self.assertIn("несовместимы", r["error"])

    def test_error_not_saved(self):
        r = self.check(self.f("s.docx", "Мало слов."), "S")
        self.assertFalse(r["saved"])

    def test_unexpected_exception(self):
        import originality.pipeline as P
        orig = P.extract_document
        P.extract_document = lambda path: 1 / 0
        try:
            r = self.check(self.f("a.docx", BASE), "A")
        finally:
            P.extract_document = orig
        self.assertEqual(r["status"], "error")
        self.assertIn("Непредвиденная ошибка", r["error"])
        self.assertIn("ZeroDivisionError", r["error"])

    def test_broken_settings_file(self):
        import originality.config as C
        from pathlib import Path
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "settings.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        old_root, C.ROOT = C.ROOT, Path(folder)
        try:
            r = check_work(self.f("a.docx", BASE), "A", None, self.emb)
        finally:
            C.ROOT = old_root
            shutil.rmtree(folder, ignore_errors=True)
        self.assertEqual(r["status"], "error")
        self.assertIn("settings.json", r["error"])
        self.assertIsNone(r["threshold_percent"])


class TestReports(Base):
    def _plag(self):
        self.add(self.f("a.docx", BASE), "A")
        return self.check(self.f("b.docx", BASE), "B")

    def test_json_roundtrip(self):
        r = self._plag()
        back = json.loads(to_json(r))
        self.assertEqual(back["work_id"], "B")
        self.assertIn("Возвращена", back["verdict"])

    def test_text_report_sections(self):
        t = to_text_report(self._plag())
        for part in ("Вердикт:", "Заимствований:", "--- Совпадение 1 ---", "Причина:"):
            self.assertIn(part, t)

    def test_text_report_error(self):
        t = to_text_report(self.check(os.path.join(self.tmp, "no.docx"), "X"))
        self.assertIn("ОШИБКА", t)
        self.assertIn("Вердикт не вынесен", t)

    def test_reason_exact_mentions_threshold(self):
        r = self._plag()
        self.assertIn("Дословное", r["matches"][0]["reason"])


class TestLog(Base):
    def test_log_written(self):
        self.check(self.f("a.docx", BASE), "A")
        with open(self.s["log_path"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Начало: A", text)
        self.assertIn("Конец: A", text)

    def test_logger_switches_path(self):
        a, b = os.path.join(self.tmp, "1.log"), os.path.join(self.tmp, "2.log")
        get_logger(a).info("x"); get_logger(b).info("y")
        with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
            self.assertNotIn("y", fa.read())
            self.assertIn("y", fb.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)