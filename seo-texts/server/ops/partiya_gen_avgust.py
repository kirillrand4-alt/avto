# -*- coding: utf-8 -*-
"""partiya_gen.py, но с каноном августа: перед запуском драйвера модуль
sender.ai_letter подменяется копией ai_letter_avgust.py (25.08.2026). Всё
остальное — отбор, заслоны очереди, журнал, резюм — штатное. Аргументы те же,
что у partiya_gen.py. Панель и её ai_letter.py не трогаются."""
import importlib.util
import runpy
import sys

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import sender  # noqa: E402

_сп = importlib.util.spec_from_file_location("sender.ai_letter", r"C:\sender\server\ops\ai_letter_avgust.py")
_мод = importlib.util.module_from_spec(_сп)
sys.modules["sender.ai_letter"] = _мод
_сп.loader.exec_module(_мод)
sender.ai_letter = _мод
print("канон августа: правила КЦ", len(_мод.RULES_KC), "знаков")
sys.argv = [r"C:\sender\server\ops\partiya_gen.py"] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
