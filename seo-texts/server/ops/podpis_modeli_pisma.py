# -*- coding: utf-8 -*-
"""Подпись «кто писал письмо»: модель черновиков — в инфо-панель письма.

Владелец 12.10: «как есть оставь, только сделай подпись кто писал письмо».
Генератор выбрасывал пометку модели (default_caller возвращает её вторым
значением), поэтому после сбоя opus и перехода на запасную sonnet нельзя
было узнать, какие письма она написала.

Как: вызов, пишущий письмо, кладёт использованную модель в список своего
потока; батч обнуляет список перед генерацией, а каждое письмо батча
получает в panel_json ключ `model_pisma`. Внутри генератора потоков нет —
черновики идут в том же потоке, что и батч, так что следы не путаются.

Хирургия по якорям ЖИВОГО файла: .bak, правка, компиляция, импорт, откат.
"""
import io
import os
import py_compile
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender\ai_quota.py"
т = io.open(ПУТЬ, encoding="utf-8").read()

if "model_pisma" in т:
    print("подпись модели уже стоит — ничего не делаю")
    print("=== ПОДПИСЬ МОДЕЛИ ПИСЬМА: УЖЕ БЫЛА ===")
    sys.exit(0)

ЗАМЕНЫ = [
    # 1. вызов, пишущий письмо, оставляет след модели
    ("""            text, _meta = default_caller(prompt, max_tokens=8000)
            return text
""",
     """            text, _meta = default_caller(prompt, max_tokens=8000)
            # ПОДПИСЬ «КТО ПИСАЛ» (владелец 12.10). _meta — модель, которая
            # реально ответила: при трёх отказах opus это запасная sonnet.
            _след = getattr(_МОДЕЛЬ_ПИСЬМА, "список", None)
            if _след is not None:
                _след.append(str(_meta or ""))
            return text
"""),
    # 2. батч обнуляет след перед генерацией
    ("""            try:
                out = self._gen_factory().generate(reqs)
""",
     """            _МОДЕЛЬ_ПИСЬМА.список = []
            try:
                out = self._gen_factory().generate(reqs)
"""),
    # 3. каждое письмо батча получает подпись в панели
    ("""                                    panel=self._panel(r, letter, day, reqs[j]))
""",
     """                                    panel=_s_podpisyu(
                                        self._panel(r, letter, day, reqs[j])))
"""),
]
нет = [с for с, _ in ЗАМЕНЫ if т.count(с) != 1]
print("якорей: %d, не сошлось: %d" % (len(ЗАМЕНЫ), len(нет)))
for с in нет:
    print("   НЕТ (%d шт): %s" % (т.count(с), с.strip()[:80]))

ЯКОРЬ_МОДУЛЯ = "def статус_брака(причины) -> str:"
if т.count(ЯКОРЬ_МОДУЛЯ) != 1:
    нет.append(ЯКОРЬ_МОДУЛЯ)
    print("   НЕТ якоря модуля: %s" % ЯКОРЬ_МОДУЛЯ)

if нет:
    print("ПРАВКА НЕ ПРИМЕНЕНА — живой файл разошёлся с ожиданием")
    print("=== ПОДПИСЬ МОДЕЛИ ПИСЬМА: НЕ ПРИМЕНЕНА ===")
    sys.exit(0)

бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ЗАМЕНЫ:
    т = т.replace(с, н)
т = т.replace(ЯКОРЬ_МОДУЛЯ, '''import threading as _threading

# Подпись «кто писал письмо» (владелец 12.10). Список моделей, ответивших
# на вызовы-черновики текущего батча; у каждого потока свой.
_МОДЕЛЬ_ПИСЬМА = _threading.local()


def _podpis_modeli() -> str:
    """«claude-opus-4-8» или «claude-opus-4-8 + claude-sonnet-4-6»."""
    след = [м for м in (getattr(_МОДЕЛЬ_ПИСЬМА, "список", None) or []) if м]
    if not след:
        return ""
    порядок = []
    for м in след:
        if м not in порядок:
            порядок.append(м)
    return " + ".join(порядок)


def _s_podpisyu(панель):
    """Добавить подпись модели в инфо-панель письма, не ломая её."""
    try:
        if isinstance(панель, dict):
            подпись = _podpis_modeli()
            if подпись:
                панель["model_pisma"] = подпись
    except Exception:  # noqa: BLE001 - подпись не должна ронять очередь
        pass
    return панель


''' + ЯКОРЬ_МОДУЛЯ, 1)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)

try:
    py_compile.compile(ПУТЬ, doraise=True)
    import importlib.util as _iu
    сп = _iu.spec_from_file_location("ai_quota_svezh", ПУТЬ)
    м = _iu.module_from_spec(сп)
    sys.path.insert(0, r"C:\sender")
    sys.modules["ai_quota_svezh"] = м
    сп.loader.exec_module(м)
    м._МОДЕЛЬ_ПИСЬМА.список = ["claude-opus-4-8", "claude-opus-4-8"]
    п1 = м._s_podpisyu({"ai": True})
    м._МОДЕЛЬ_ПИСЬМА.список = ["claude-opus-4-8", "claude-sonnet-4-6"]
    п2 = м._s_podpisyu({"ai": True})
    м._МОДЕЛЬ_ПИСЬМА.список = []
    п3 = м._s_podpisyu({"ai": True})
    print("   проверка: оба opus      -> %r" % п1.get("model_pisma"))
    print("   проверка: с запасной    -> %r" % п2.get("model_pisma"))
    print("   проверка: следа нет     -> %r" % п3.get("model_pisma"))
    assert п1["model_pisma"] == "claude-opus-4-8"
    assert "sonnet" in п2["model_pisma"]
    assert "model_pisma" not in п3
    print("   ПРАВКА ПРИМЕНЕНА, бэкап %s" % os.path.basename(бэкап))
    print("=== ПОДПИСЬ МОДЕЛИ ПИСЬМА: ПРИМЕНЕНА ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("   ОТКАТ: %s" % e)
    print("=== ПОДПИСЬ МОДЕЛИ ПИСЬМА: ОТКАТ ===")
