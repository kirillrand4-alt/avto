# -*- coding: utf-8 -*-
"""Брак яруса C по категориям: что лечится перегенерацией, что починкой текста,
что не лечится. Берём ПОСЛЕДНЮЮ попытку по ИНН без письма. Только чтение."""
import io
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
с_письмом = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.extra_json LIKE '%v4-C%'")}
посл = {}
for s in io.open(r"C:\sender\_ops\gen-v4c.jsonl", encoding="utf-8"):
    try:
        z = json.loads(s)
    except ValueError:
        continue
    if z.get("inn"):
        посл[str(z["inn"])] = z
кат, причины = Counter(), Counter()
for инн, z in посл.items():
    if инн in с_письмом or z.get("ок"):
        continue
    бр = " | ".join(str(b) for b in (z.get("брак") or []))
    н = бр.lower()
    if "403" in н or "прогон упал" in н or "json" in н or "таймаут" in н or "timeout" in н:
        к = "техсбой — перегенерировать"
    elif "не покупатель" in н or "переставить на kc" in н or "не наш" in н:
        к = "не покупатель / не Meyer — не лечится (или в КЦ)"
    elif any(w in н for w in ("редактор", "не названо", "регламент", "компонент", "длинн", "канцел", "заход", "штамп", "тире", "повтор")):
        к = "правило текста — починка"
    elif not бр:
        к = "без причины в журнале"
    else:
        к = "прочее"
    кат[к] += 1
    причины[(к, (z.get("брак") or ["—"])[0][:60] if z.get("брак") else "—")] += 1
print("попыток без письма (последняя по ИНН):", sum(кат.values()))
for k, n in кат.most_common():
    print("  %4d  %s" % (n, k))
print("\nчастые причины:")
for (к, п), n in причины.most_common(18):
    print("  %4d  [%s] %s" % (n, к[:14], п))
