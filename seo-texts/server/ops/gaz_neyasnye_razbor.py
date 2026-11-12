# -*- coding: utf-8 -*-
"""Разбор адресов кампании 22 с вердиктом «неясно»/«отказ пробе»: ответы серверов, IP в отказах, время пробы. Только чтение."""
import re, socket, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
кол = [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")]
print("колонки addr_probe:", кол)
ряды = c.execute("SELECT DISTINCT lower(r.email) FROM confirm_reviews r WHERE r.campaign_id=22").fetchall()
вер = {}
for р in c.execute("SELECT * FROM addr_probe"):
    д = dict(zip(кол, р)); вер[str(д.get("email") or "").lower()] = д
ip = Counter(); дни = Counter(); прим = []
for (em,) in ряды:
    д = вер.get(em)
    if not д or д.get("verdict") not in ("неясно", "отказ пробе"): continue
    а = str(д.get("answer") or "")
    for x in re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", а): ip[x] += 1
    дни[str(д.get("ts") or д.get("checked_at") or "")[:13]] += 1
    if len(прим) < 12 and re.search(r"hostname|PTR|reverse|rDNS|helo", а, re.I): прим.append(а[:220])
print("IP в ответах:", ip.most_common(10))
print("время пробы (час):", sorted(дни.items())[:40])
print("примеры отказов по имени хоста:"); [print("  ", x) for x in прим]
print("getfqdn сервера:", socket.getfqdn())
try: print("PTR 91.206.14.169:", socket.gethostbyaddr("91.206.14.169"))
except Exception as ex: print("PTR ошибка:", ex)
