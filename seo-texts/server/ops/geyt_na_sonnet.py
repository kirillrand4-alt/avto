# -*- coding: utf-8 -*-
"""Гейт покупателя и судья идей захода — на модель проверок (sonnet).

Владелец 12.10: «сначала перестанем жечь деньги просто так». Журнал шлюза:
opus-вызовы 23–35 тыс. токенов на вход и 84–306 на выход, $0.19–0.33
каждый. Это target_gate (две торговые линзы на батч компаний) и судья
идей захода: оба зовут default_caller без модели, то есть opus. Решение
владельца 18.08 — проверки и гейт адресата на sonnet; в этих двух местах
оно так и не было сделано. Пишет письмо по-прежнему opus.
"""
import importlib.util as _iu
import io
import os
import py_compile
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
метка = int(time.time())


def править(путь, замены, проверка):
    т = io.open(путь, encoding="utf-8").read()
    нет = [с for с, _ in замены if т.count(с) != 1]
    if нет:
        for с in нет:
            print("   якорь не найден (%d): %s" % (т.count(с), с.strip()[:80]))
        return False
    бэкап = путь + ".bak-%d" % метка
    shutil.copy2(путь, бэкап)
    for с, н in замены:
        т = т.replace(с, н)
    io.open(путь, "w", encoding="utf-8").write(т)
    try:
        py_compile.compile(путь, doraise=True)
        сп = _iu.spec_from_file_location("sv_%d" % abs(hash(путь)), путь)
        м = _iu.module_from_spec(сп)
        sys.modules[сп.name] = м
        сп.loader.exec_module(м)
        проверка(м, io.open(путь, encoding="utf-8").read())
        print("   применено, бэкап %s" % os.path.basename(бэкап))
        return True
    except Exception as e:  # noqa: BLE001
        shutil.copy2(бэкап, путь)
        print("   ОТКАТ: %s" % e)
        return False


print("--- 1. гейт покупателя (target_gate) ---")
ГЕЙТ_СТАР = """        def caller(prompt: str) -> str:  # noqa: F811
            текст, _мета = default_caller(prompt)
            return текст
"""
ГЕЙТ_НОВ = """        # МОДЕЛЬ ПРОВЕРОК, НЕ OPUS (владелец 12.10: «перестанем жечь
        # деньги»; решение 18.08 — гейт адресата на sonnet). Гейт отвечает
        # коротким JSON по готовым карточкам, а шёл на opus без явной модели:
        # 23–35 тыс. токенов на вход, $0.19–0.33 за вызов.
        _модель = "claude-sonnet-4-6"
        try:
            if config is not None and hasattr(config, "get"):
                _модель = str(config.get("ai_quota.checker_model",
                                         _модель) or _модель)
        except Exception:  # noqa: BLE001
            pass

        def caller(prompt: str) -> str:  # noqa: F811
            текст, _мета = default_caller(prompt, model=_модель)
            return текст
"""


def пров_гейт(м, т):
    assert "default_caller(prompt, model=_модель)" in т


ок1 = править(r"C:\sender\sender\target_gate.py", [(ГЕЙТ_СТАР, ГЕЙТ_НОВ)], пров_гейт)

print("--- 2. судья идей захода (ai_quota) ---")
ИДЕЯ_СТАР = """                суд, _ = default_caller(
                    "Выбери ОДНУ лучшую идею захода холодного письма для этой "
"""
ИДЕЯ_НОВ = """                # Судья идей — проверка, не письмо: модель проверок
                # (владелец 12.10, решение 18.08), а не opus по умолчанию.
                суд, _ = default_caller(
                    model=str(self._config.get("ai_quota.checker_model",
                                               "claude-sonnet-4-6")
                              or "claude-sonnet-4-6"),
                    prompt=
                    "Выбери ОДНУ лучшую идею захода холодного письма для этой "
"""


def пров_идея(м, т):
    assert 'model=str(self._config.get("ai_quota.checker_model"' in т


ок2 = править(r"C:\sender\sender\ai_quota.py", [(ИДЕЯ_СТАР, ИДЕЯ_НОВ)], пров_идея)
print("")
print("=== ГЕЙТ И СУДЬЯ ИДЕЙ НА SONNET: гейт %s, судья %s ==="
      % ("ок" if ок1 else "НЕТ", "ок" if ок2 else "НЕТ"))
