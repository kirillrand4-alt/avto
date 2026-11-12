# -*- coding: utf-8 -*-
"""Сколько адресов из входа ещё не в журнале пробы и по каким доменам. Только чтение."""
import io, json
from collections import Counter
вход = set()
for с in io.open(r"C:\sender\_ops\meyer-provaly2.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if not x.get("stop"): вход |= {e.strip().lower() for e in x.get("emails") or []}
ж = {json.loads(с)["email"] for с in io.open(r"C:\sender\_ops\proba-meyer-provaly.jsonl", encoding="utf-8")}
ост = вход - ж
print("во входе %d, в журнале %d, осталось %d" % (len(вход), len(ж & вход), len(ост)))
print("по доменам:", Counter(e.rsplit("@", 1)[-1] for e in ост).most_common(10))
д = Counter()
for с in io.open(r"C:\sender\_ops\proba-meyer-provaly.jsonl", encoding="utf-8"):
    x = json.loads(с); дм = x["email"].rsplit("@", 1)[-1]
    if дм in ("yandex.ru", "ya.ru", "rambler.ru", "mail.ru"): д[(дм, x["krug"], x["itog"], str(x.get("otvet", ""))[:45])] += 1
for к, v in sorted(д.items()): print("  ", к, v)
