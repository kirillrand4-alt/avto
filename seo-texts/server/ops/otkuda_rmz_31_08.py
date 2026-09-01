# -*- coding: utf-8 -*-
"""Только чтение: из какого прогона пришёл РМЗ и что говорит база фактов Meyer."""
import io
import json
import os
import sys

ИНН = "7449143960"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
print("=== СТРОКИ ЖУРНАЛА ПО ИНН %s ===" % ИНН)
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:
            continue
        if str(z.get("inn")) == ИНН:
            print("  день=%s напр=%s ок=%s модель=%s сек=%s цена=%s"
                  % (z.get("день"), z.get("направление"), z.get("ок"),
                     z.get("модель"), z.get("сек"), z.get("цена_$")))
            if z.get("напр_почему"):
                print("     почему направление: %s" % str(z["напр_почему"])[:200])
            if z.get("брак"):
                print("     брак: %s" % str(z["брак"])[:200])

print("\n=== ЛОГИ ПРОГОНОВ 31.08 ПОСЛЕ 17:00 ===")
import glob
import datetime
for л in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
                key=os.path.getmtime, reverse=True)[:6]:
    т = datetime.datetime.fromtimestamp(os.path.getmtime(л))
    голова = io.open(л, encoding="utf-8", errors="replace").read().splitlines()[:10]
    гр = [x for x in голова if "в группе" in x]
    print("  %s  %-34s %s" % (т.strftime("%m-%d %H:%M"), os.path.basename(л),
                              гр[0].strip() if гр else ""))

print("\n=== ЧТО ПРОДАЁТ MEYER ПО БАЗЕ ФАКТОВ ===")
sys.path.insert(0, r"C:\sender")
try:
    from sender.ai_letter import load_facts  # noqa: E402
    f = load_facts(division="meyer")
    t = f if isinstance(f, str) else json.dumps(f, ensure_ascii=False)
    for x in t.splitlines()[:26]:
        print("  " + x[:112])
except Exception as ex:
    print("  ", str(ex)[:120])
