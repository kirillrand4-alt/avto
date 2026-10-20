# -*- coding: utf-8 -*-
"""Проверка сравнения «старый/новый стиль КЦ» (владелец 20.10). Стиль — по ТЕКСТУ
письма, а не по имени кампании: новый = «Меня зовут …»/«представляю компанию»
(канон 16.10+), старый = без представления по имени. Ответ — строго на это
письмо (events.message_id), только люди. Плюс равное окно: ответ в первые 3 суток."""
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
отв = defaultdict(list)
for mid, ts in c.execute("SELECT message_id, event_ts FROM events WHERE event_type='reply' AND message_id IS NOT NULL"):
    отв[mid].append(str(ts))


def стиль(тело):
    т = str(тело or "")
    if re.search(r"Меня зовут|представляю компанию|представляю «Компрессор", т):
        return "новый"
    return "старый"


кол = {r[1] for r in c.execute("PRAGMA table_info(messages)")}
поле = "body_rendered" if "body_rendered" in кол else "body"
сч = defaultdict(lambda: [0, 0, 0])
for mid, cid, mb, sa, тело in c.execute("SELECT id, campaign_id, mailbox_id, sent_at, %s FROM messages WHERE status='sent'" % поле):
    if "ompressor" not in str(mb):
        continue
    к = (стиль(тело), кам.get(cid, cid), str(sa)[:7])
    сч[к][0] += 1
    if отв.get(mid):
        сч[к][1] += 1
        try:
            d = (datetime.fromisoformat(min(отв[mid])[:19]) - datetime.fromisoformat(str(sa)[:19])).total_seconds()
            if d <= 3 * 86400:
                сч[к][2] += 1
        except Exception:  # noqa: BLE001
            pass
print("%-6s %-30s %-7s %6s %6s %6s %8s" % ("стиль", "кампания", "месяц", "ушло", "ответ", "%", "за 3 сут"))
ит = defaultdict(lambda: [0, 0, 0])
for к in sorted(сч, key=lambda k: (k[0], k[2], str(k[1]))):
    n, r, r3 = сч[к]
    if n < 10:
        continue
    print("%-6s %-30s %-7s %6d %6d %5.2f%% %4d %5.2f%%" % (к[0], str(к[1])[:30], к[2], n, r, 100 * r / n, r3, 100 * r3 / n))
    for i in range(3):
        ит[к[0]][i] += сч[к][i]
for s, (n, r, r3) in ит.items():
    print("ИТОГО %-6s ушло %5d ответов %4d (%.2f%%), за 3 суток %4d (%.2f%%)" % (s, n, r, 100 * r / n, r3, 100 * r3 / n))
