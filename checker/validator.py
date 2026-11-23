"""Запуск двух частей проверки параллельно."""
from concurrent.futures import ThreadPoolExecutor

from .param_check import check_params
from .structure_check import check_structure


def run_checks(parsed, kb):
    with ThreadPoolExecutor(max_workers=2) as pool:
        params = pool.submit(check_params, parsed["facts"], kb)
        structure = pool.submit(check_structure, parsed["structure"], kb)
        # result() пробросит исключение, если одна из частей упала
        return params.result() + structure.result()
