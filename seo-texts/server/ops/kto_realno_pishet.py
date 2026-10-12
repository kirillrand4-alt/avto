# -*- coding: utf-8 -*-
"""Кто РЕАЛЬНО написал последние письма: следы модели в живом коде и базе.

Владелец 12.10: «я помню что последние письма писал соннет». По умолчанию
кода письмо пишет opus-4-8, но генератор выбрасывает пометку модели, и
по умолчанию не видно, что было на деле. Ищем все места, где модель могла
подмениться, и все места, где она могла записаться.
"""
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

print("--- где в живом коде упоминается sonnet / выбор модели письма ---")
for корень in (r"C:\sender\sender", r"C:\sender"):
    for имя in sorted(os.listdir(корень)):
        if not имя.endswith(".py"):
            continue
        п = os.path.join(корень, имя)
        try:
            т = io.open(п, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        for н, с in enumerate(т.splitlines(), 1):
            if re.search(r"(?i)sonnet|LETTER_MODEL|WRITER_MODEL|"
                         r"model\s*=\s*model\s+or|\.get\(['\"]ai_quota\.model",
                         с) and not с.strip().startswith("#"):
                print("   %-22s:%-5d %s" % (имя[:22], н, с.strip()[:90]))

print("")
print("--- ключи ai_quota в конфиге целиком ---")
т = io.open(r"C:\sender\sender.yaml", encoding="utf-8").read()
блок = re.search(r"(?ms)^ai_quota:\s*\n((?:[ \t]+.*\n?)+)", т)
print(блок.group(1) if блок else "   (раздела ai_quota нет)")

print("--- есть ли модель в данных писем ---")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for р in c.execute("SELECT id, created_at, panel_json FROM confirm_reviews "
                   "WHERE kind='outbound' ORDER BY id DESC LIMIT 400"):
    пj = str(р["panel_json"] or "")
    м = re.findall(r'"(?:model|модель|used_model|writer_model)"\s*:\s*"([^"]+)"', пj)
    if м:
        print("   review #%s %s -> %s" % (р["id"], р["created_at"][:16],
                                         ", ".join(sorted(set(м)))))
        break
else:
    print("   в panel_json последних 400 писем модели нет")
таблицы = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
for т_ in таблицы:
    кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т_)]
    if any("model" in к.lower() for к in кол):
        print("   таблица %s, колонки с моделью: %s"
              % (т_, [к for к in кол if "model" in к.lower()]))
print("")
print("=== КТО ПИШЕТ ПИСЬМА ===")
