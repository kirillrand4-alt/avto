# -*- coding: utf-8 -*-
"""Причины брака в текущем запуске КЦ-1 (строки журнала после последнего
«ЗАПУСК» в логе — по времени старта): сколько попыток, годных, по причинам."""
import io
import json
import re
from collections import Counter

лог = io.open(r"C:\sender\_ops\gen-kc1-avgust.log", encoding="utf-8", errors="replace").read()
старт = re.findall(r"==== ЗАПУСК (\d\d:\d\d:\d\d)", лог)[-1]
итоги = [json.loads(s) for s in io.open(r"C:\sender\_ops\gen-kc1-avgust.jsonl", encoding="utf-8") if '"итог"' in s]
# запуск сегодня: берём хвост журнала с тем же числом строк, что в логе после старта
хвост = лог[лог.rfind("==== ЗАПУСК"):]
n = len(re.findall(r"\[\d+/\d+\]", хвост))
x = итоги[-n:] if n else []
сч = Counter()
for z in x:
    if z.get("ок"):
        continue
    п = (z.get("брак") or ["?"])[0]
    п = re.sub(r"«.*", "", п)
    п = re.sub(r"\d+ слов", "N слов", п)
    сч[п.strip()[:70]] += 1
print("запуск с", старт, "| попыток", len(x), "| годных", sum(1 for z in x if z.get("ок")), "| брак", len(x) - sum(1 for z in x if z.get("ок")))
for k, v in сч.most_common(12):
    print("  %4d  %s" % (v, k))
