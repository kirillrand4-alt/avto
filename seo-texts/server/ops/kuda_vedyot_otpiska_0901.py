# -*- coding: utf-8 -*-
"""Только чтение: что за заголовок List-Unsubscribe и куда он ведёт."""
import io
import re
import sqlite3

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
print("=== List-Unsubscribe В КОДЕ ===")
пок = set()
for i, x in enumerate(стр):
    if "List-Unsubscribe" in x or "unsub_token" in x:
        н = max(0, i - 6)
        if н in пок:
            continue
        пок.add(н)
        print("  --- sender.py:%d ---" % (i + 1))
        for j in range(н, min(i + 8, len(стр))):
            print("     %4d  %s" % (j + 1, стр[j][:106]))
        print()

print("=== ОТКУДА БЕРЁТСЯ АДРЕС ОТПИСКИ ===")
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("unsub", "unsubscribe", "compliance", "links", "public_url", "base_url"):
    try:
        v = cfg.get(к)
        if v:
            print("  %-20s = %r" % (к, str(v)[:150]))
    except Exception:
        pass

print("\n=== ИТОГ: ТЕЛО ПИСЬМА — ЕСТЬ ЛИ ТАМ СЛОВО ОБ ОТПИСКЕ ===")
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
n = 0
всего = 0
for р in s.execute("SELECT body FROM confirm_reviews WHERE status IN ('sent','approved')"
                   " ORDER BY id DESC LIMIT 300"):
    t = str(р["body"] or "").lower()
    всего += 1
    if "отпис" in t or "unsubscrib" in t:
        n += 1
print("  писем просмотрено: %d, со словом об отписке в ТЕЛЕ: %d" % (всего, n))
print("  (заголовок List-Unsubscribe в теле не виден — его показывает почтовик)")
