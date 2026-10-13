# -*- coding: utf-8 -*-
"""Отказы модели писать письмо («I can't…») по всем журналам: сколько, у скольких
компаний, сколько денег, по отраслям и по формулировке (рассылка/спам/обман)."""
import io
import json
import re
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег = {str(р[0]): р[1] for р in c.execute("SELECT inn, segment FROM recipients WHERE inn IS NOT NULL")}
for журнал in (r"C:\sender\_ops\gen-partiya-935.jsonl", r"C:\sender\_ops\gen-rossiya-9000.jsonl"):
    поп, комп, деньги, отр, фраз, дни = 0, set(), 0.0, Counter(), Counter(), Counter()
    всего = 0
    видели = set()
    for с in io.open(журнал, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        if z.get("этап") != "итог":
            continue
        к = (z.get("recipient_id"), z.get("цена_$"), z.get("сек"))
        if к in видели:
            continue
        видели.add(к)
        всего += 1
        б = " ".join(str(x) for x in (z.get("брак") or []))
        if "I can" not in б and "I cannot" not in б and "I won" not in б:
            continue
        поп += 1
        комп.add(z.get("inn"))
        деньги += float(z.get("цена_$") or 0)
        отр[сег.get(str(z.get("inn")), "?")] += 1
        дни[str(z.get("день"))] += 1
        low = б.lower()
        фраз["рассылка/cold emails/mass mailing" if re.search(r"mass mail|cold (email|outreach)|spam|bulk", low) else
             "обман/выдать за личное" if re.search(r"decept|disguis|mimic|pretend|personal", low) else "прочее"] += 1
    print("%s: попыток всего %d, отказов %d (%.1f%%), компаний %d, потрачено на отказы $%.2f" % (
        журнал.split("\\")[-1], всего, поп, 100.0 * поп / max(1, всего), len(комп), деньги))
    print("   формулировка: %s" % dict(фраз))
    print("   по дням: %s" % dict(sorted(дни.items())[-6:]))
    print("   по отраслям: %s" % dict(отр.most_common(8)))
print("=== ОТКАЗЫ МОДЕЛИ ===")
