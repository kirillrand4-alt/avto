# -*- coding: utf-8 -*-
"""Показать письма партии «Агро зерно 2026» из очереди подтверждения — глазами.

Владелец 07.09: «проверь глазами выборочно штук 30, если будут ошибки
исправляй пока последняя проверка глазами не выдаст результат без ошибок».

    python glaza_agro.py [сколько=30] [--vse-podryad]
"""
import io, json, os, random, sys
sys.path.insert(0, r"C:\sender")

ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
СКОЛЬКО = 30
for а in sys.argv[1:]:
    if а.startswith(("сколько=", "skolko=")):
        try:
            СКОЛЬКО = int(а.split("=", 1)[1])
        except ValueError:
            pass
ПОДРЯД = "--vse-podryad" in sys.argv

строки = []
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("review_id") and z.get("тело"):
            строки.append(z)
print("писем в журнале очереди: %d" % len(строки))
if not строки:
    raise SystemExit(0)
выбор = строки[:СКОЛЬКО] if ПОДРЯД else random.sample(
    строки, min(СКОЛЬКО, len(строки)))
for n, z in enumerate(выбор, 1):
    print("")
    print("#" * 78)
    print("# %d/%d  review %s | ИНН %s | %s"
          % (n, len(выбор), z.get("review_id"), z.get("инн"), z.get("почта")))
    print("# реестр: %s" % z.get("имя_реестра"))
    print("#" * 78)
    print("Тема: %s" % z.get("тема"))
    print("")
    print(z.get("тело"))
