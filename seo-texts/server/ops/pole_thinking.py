# -*- coding: utf-8 -*-
"""Переключатель поля thinking в клиенте шлюза (gen_provider._raw_stream).

Опыт 12.10 на канале Claude Kiro (sonnet-4-6 и opus-4-8, один промпт):
  thinking={'type':'disabled'} + усилие low  -> 870-895 ток, рассуждение ~2100 зн
  поля thinking нет вовсе (+ усилие low/med) -> 52-290 ток, рассуждение 0
То есть этот канал ВКЛЮЧАЕТ рассуждение, увидев любое поле thinking, — ровно
наоборот замеру 17.08 на прежнем канале, где без поля модель рассуждала.

PROVIDER_THINKING_FIELD: disabled (по умолчанию, как было) | omit (поле не
слать). Умолчание не меняем: клиентом пользуются панель и соседние задания,
а на другом канале правильным бывает как раз явный запрет.
"""
import importlib.util as _iu
import io
import os
import py_compile
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
ПУТЬ = r"C:\sender\gen_provider.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
СТАР = """        body['thinking'] = ({'type': 'adaptive'} if thinking
                            else {'type': 'disabled'})
"""
НОВ = """        # ПОЛЕ THINKING — ПОД КАНАЛ (12.10). Канал Claude Kiro, увидев ЛЮБОЕ
        # поле thinking (даже disabled), включает рассуждение: 870 токенов
        # выхода и ~2100 знаков рассуждения против 52-290 токенов и нуля без
        # поля. На прежнем канале (17.08) было наоборот. Поэтому переключатель:
        # PROVIDER_THINKING_FIELD=omit — не слать поле при thinking=False.
        if thinking:
            body['thinking'] = {'type': 'adaptive'}
        elif (os.environ.get('PROVIDER_THINKING_FIELD') or 'disabled'
              ).strip().lower() != 'omit':
            body['thinking'] = {'type': 'disabled'}
"""
if "PROVIDER_THINKING_FIELD" in т:
    print("переключатель уже стоит")
    print("=== ПОЛЕ THINKING: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(СТАР) != 1:
    print("якорь не найден (%d)" % т.count(СТАР))
    print("=== ПОЛЕ THINKING: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    for режим in ("disabled", "omit"):
        os.environ["PROVIDER_THINKING_FIELD"] = режим
        сп = _iu.spec_from_file_location("gp_" + режим, ПУТЬ)
        м = _iu.module_from_spec(сп)
        sys.modules[сп.name] = м
        сп.loader.exec_module(м)
        t = time.time()
        о = м._raw_stream([{"role": "user", "content":
                            "Одной фразой: зачем мельнице фотосепаратор?"}],
                          "claude-sonnet-4-6", 600, thinking=False, effort="low")
        блоки = [getattr(б, "type", "?") for б in о.content]
        print("   режим %-8s блоки %s, выход %s ток, %.1f с"
              % (режим, блоки, getattr(о.usage, "output_tokens", "?"), time.time() - t))
    print("ПРИМЕНЕНО, бэкап %s" % os.path.basename(бэкап))
    print("=== ПОЛЕ THINKING: ПРИМЕНЕНО ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("ОТКАТ: %s" % e)
    print("=== ПОЛЕ THINKING: ОТКАТ ===")
