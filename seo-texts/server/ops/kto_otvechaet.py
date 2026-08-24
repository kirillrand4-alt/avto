# -*- coding: utf-8 -*-
"""Кто из моделей отвечает ПРЯМО СЕЙЧАС — одна попытка, без ретраев.

Гейт адресата встал потому, что запасная модель линзы (claude-opus-4-7)
молчит: стрим шлёт только ping. Прежде чем закреплять другую модель, надо
знать, кто жив. Ретраи здесь выключены нарочно — замер должен занять
минуту, а не одиннадцать.

Заодно снимает мои же зависшие замеры model_zhiva_li.py: они сидят в
восьми ретраях с паузами и жгут деньги впустую.
"""
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402

print("=== СНИМАЮ ЗАВИСШИЕ ЗАМЕРЫ ===")
вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'",
     "get", "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
цель, ком = [], ""
for строка in вывод.splitlines():
    строка = строка.strip()
    if строка.startswith("CommandLine="):
        ком = строка
    elif строка.startswith("ProcessId=") and "model_zhiva_li.py" in ком:
        цель.append(строка.split("=", 1)[1])
for пид in цель:
    r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                       capture_output=True, text=True, timeout=60)
    print("  снят %s: rc=%s" % (пид, r.returncode))
if not цель:
    print("  зависших замеров нет")

print("\n=== КТО ОТВЕЧАЕТ (одна попытка, стрим) ===")
ЗАПРОС = [{"role": "user", "content": "Ответь одним словом: готов"}]
for модель in ("claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6",
               "claude-haiku-4-5", "claude-fable-5",
               # дешёвые судьи предклассификатора: владелец 24.08 помнит,
               # что судила луна. Она замолчала 20.08, цепочка ушла на
               # mini -> haiku -> gemini, и сегодня в логах мертвы все три.
               "gpt-5.6-luna", "gpt-5.4-mini", "gemini-3-flash"):
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(ЗАПРОС, модель, 32, thinking=False)
        т = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
        print("%-20s ОТВЕТИЛА  %5.1f c  %r" % (модель, time.time() - т0, т[:40]))
    except Exception as e:                                     # noqa: BLE001
        print("%-20s МОЛЧИТ    %5.1f c  %s: %s"
              % (модель, time.time() - т0, type(e).__name__, str(e)[:150]))
