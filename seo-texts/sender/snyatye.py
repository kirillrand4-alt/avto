"""Стоп-лист снятых с производства серий (kb/snyatye-verdict.json).

Давний незакрытый пункт, закрыт в ENGINEER-TASKS-CONFIRM-SEND: письмо не
должно предлагать серию, снятую заводом. Вердикты файла:
  снята_заводом      — жёсткий стоп (те самые «17 серий», красный флаг);
  снята_у_конкурента — слабый сигнал (низкая conf, у нас модель жива) — жёлтый;
  мало_данных        — не сигнал.

API: stop_series() -> {(brand, series)}, scan_text(text) -> находки в тексте.
Подключено: инфо-панель confirm-send (красная полоса) и qa_reply автоответчика.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_KB_PATH = Path(__file__).resolve().parents[1] / "kb" / "snyatye-verdict.json"

_HARD = "снята_заводом"
_SOFT = "снята_у_конкурента"

_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - нет файла (урезанное окружение)
            _cache = {}
    return _cache


def stop_series(*, hard_only: bool = True) -> set[tuple[str, str]]:
    """Множество (бренд, серия) снятых. hard_only=True — только снята_заводом."""
    out: set[tuple[str, str]] = set()
    for brand, data in _load().items():
        for s in data.get("series") or []:
            v = str(s.get("verdict") or "")
            if v == _HARD or (not hard_only and v == _SOFT):
                out.add((brand, str(s.get("series") or "")))
    return out


def _series_pattern(series: str) -> re.Pattern:
    """Серия в тексте письма: регистронезависимо, пробелы/дефисы между
    буквенной и цифровой частью допускаются (ВК20 == ВК-20 == ВК 20).

    Границы: слева не буква/цифра; справа не буква/цифра И не «.цифра»
    (DL1 не должен ловить DL1.8), но точка конца предложения — допустима.
    """
    esc = re.escape(series)
    esc = esc.replace(r"\-", r"[-\s]?")
    # стык буква→цифра и цифра→буква может быть разорван пробелом/дефисом
    esc = re.sub(r"(?<=[А-ЯA-Zа-яa-z])(?=\d)", r"[-\\s]?", esc)
    return re.compile(rf"(?<!\w){esc}(?!\w|\.\d)", re.IGNORECASE)


def scan_text(text: str, *, include_soft: bool = True) -> list[dict]:
    """Упоминания снятых серий в тексте.

    Возврат: [{brand, series, verdict, severity: red|yellow}] — red для
    снятых заводом, yellow для снятых у конкурента (если include_soft).
    """
    if not text:
        return []
    found: list[dict] = []
    for brand, data in _load().items():
        for s in data.get("series") or []:
            v = str(s.get("verdict") or "")
            if v == _HARD:
                sev = "red"
            elif v == _SOFT and include_soft:
                sev = "yellow"
            else:
                continue
            series = str(s.get("series") or "")
            if len(series) < 3:
                continue  # короткие коды дают ложняки на любом тексте
            if _series_pattern(series).search(text):
                found.append({"brand": brand, "series": series,
                              "verdict": v, "severity": sev})
    return found


def qa_stop_series_problems(text: str) -> list[str]:
    """Формат для QA-гейтов (список строк-проблем): только жёсткий стоп."""
    return [
        f"снятая с производства серия в тексте: {f['brand']} {f['series']} "
        f"({f['verdict']})"
        for f in scan_text(text, include_soft=False)
    ]
