# -*- coding: utf-8 -*-
"""Из чего состоит брак генерации: что про компанию, а что про ротацию.

Важно для вопроса «кого не генерировать»: если брак в основном про
исчерпанные заходы, то отбор компаний тут не поможет вовсе - это про
партию, а не про адресата.
"""
import io
import json
import re
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
c = Counter()
всего = 0
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "отмена_попытки" or z.get("ок") or z.get("тело"):
        continue
    причина = " | ".join(str(x) for x in (z.get("брак") or []))
    if not причина.strip():
        continue
    всего += 1
    п = причина.lower()
    if "израсходован" in п or "анти-штамп" in п:
        c["ротация заходов (не про компанию)"] += 1
    elif "линза" in п:
        c["инженерная линза: профиль компании"] += 1
    elif "цех не подтверждён" in п:
        c["цеха нет на сайте"] += 1
    elif "слов" in п and "норма" in п:
        c["объём письма"] += 1
    elif "нет message_id" in п or "очередь" in п:
        c["очередь/база, не модель"] += 1
    elif "403" in п or "прогон упал" in п or "timeout" in п:
        c["сбой провайдера"] += 1
    else:
        c[re.sub(r"\d+", "N", причина[:58])] += 1
print(f"записей с браком: {всего}")
for к, n in c.most_common(12):
    print(f"  {n:>5}  {к}")
