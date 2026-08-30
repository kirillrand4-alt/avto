# -*- coding: utf-8 -*-
"""Прогресс-файл сборщика: какие коды он считает пройденными."""
import io
import json
import os

п = r"C:\seostat\Parser2\data\agro-base.progress.json"
print("файл: %s (%s)" % (п, "есть" if os.path.exists(п) else "нет"))
if os.path.exists(п):
    d = json.load(io.open(п, encoding="utf-8"))
    if isinstance(d, dict):
        for к, v in list(d.items())[:5]:
            print("   ключ %r → %s" % (к, str(v)[:200]))
        коды = d.get("done") or d.get("codes") or []
    else:
        коды = d
    коды = list(коды)
    print("пройденных кодов: %d" % len(коды))
    print("   %s" % ", ".join(map(str, коды)))

print("\n=== run_once, строки 96–130 ===")
и = io.open(r"C:\seostat\Parser2\scripts\daily_collect.py",
            encoding="utf-8", errors="replace").read().splitlines()
for n in range(95, 131):
    print("%4d| %s" % (n + 1, и[n].rstrip()[:150]))
