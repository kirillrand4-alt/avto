# -*- coding: utf-8 -*-
"""Почему остановился прогон 9000: служебные записи журнала (не «итог»), последние."""
import io
import json
from collections import Counter
зап = [json.loads(с) for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8") if с.strip()]
print("этапы:", dict(Counter(з.get("этап") for з in зап[-3000:])))
import re
сыр = [с for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8") if re.search(r"заслон|бюджет|стоп|дорого|отмена|остановл|окно", с)]
print("служебных строк: %d" % len(сыр))
for с in сыр[-6:]:
    print(с[:300])
сл = []
for з in сл[-14:]:
    print(json.dumps(з, ensure_ascii=False)[:300])
print("=== ПОЧЕМУ СТОП ===")
