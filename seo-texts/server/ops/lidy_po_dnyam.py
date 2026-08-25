# -*- coding: utf-8 -*-
"""Ответы и карточки по дням: в какие дни лента вообще заводилась.

Тринадцать потерянных объясняются правкой 24.08 («вежливый отказ теперь в
ленте»), но двое были «hot» — их код тех дней завести обязан был. Смотрим,
заводились ли карточки в те же дни вообще.
"""
import json
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
по_дням = defaultdict(Counter)
for р in c.execute("SELECT event_ts, detail_json, recipient_id FROM events "
                   " WHERE event_type IN ('reply','reply_auto')"):
    d = json.loads(р["detail_json"] or "{}")
    по_дням[str(р["event_ts"])[:10]][str(d.get("reply_kind") or "нет")] += 1
    по_дням[str(р["event_ts"])[:10]]["ответов"] += 1

карточки = Counter()
for р in c.execute("SELECT created_at FROM leads"):
    карточки[str(р["created_at"])[:10]] += 1

print("%-12s %8s %8s %8s %8s %8s" % ("день", "ответов", "карточек", "hot",
                                     "отказов", "авто"))
for д in sorted(set(по_дням) | set(карточки)):
    с = по_дням.get(д, Counter())
    print("%-12s %8d %8d %8d %8d %8d"
          % (д, с["ответов"], карточки.get(д, 0), с["hot"],
             с["not_interested"], с["auto_reply"]))
