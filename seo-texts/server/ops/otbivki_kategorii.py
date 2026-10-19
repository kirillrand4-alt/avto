# -*- coding: utf-8 -*-
"""Отбивки за 7 дней по категориям: код статуса DSN, текст сервера, вид (hard/soft/policy). Только чтение."""
import json, re, sqlite3, time
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400))
def кат(st, д, вид):
    t = (д + " " + st).lower()
    if re.search(r"spam|спам|ip you|blacklist|blocklist|rbl|spamhaus|reputation|репутац", t): return "спам / репутация отправителя"
    if re.search(r"no such|unknown|not exist|не существ|recipientnotfound|user not found|5\.1\.1|5\.1\.10|invalid recipient|address rejected|mailbox unavailable|недоступ|нет такого", t): return "нет такого ящика"
    if re.search(r"quota|full|переполн|5\.2\.2|over|storage", t): return "ящик переполнен"
    if re.search(r"disabled|blocked user|suspend|inactive|заблокир|отключ|5\.2\.1", t): return "ящик заблокирован / отключён"
    if re.search(r"relay|not permitted|5\.7\.\d|policy|reject|denied|отклон", t): return "отказ по политике сервера"
    if re.search(r"dns|mx|host not found|domain|5\.1\.2|4\.4", t): return "домен / MX не найден"
    if re.search(r"timeout|time out|4\.\d\.\d|delay|задерж", t): return "временная ошибка / таймаут"
    if not д.strip() and not st.strip(): return "без текста (вид: %s)" % (вид or "?")
    return "прочее"
сч = Counter(); прим = defaultdict(list); коды = Counter()
for mb, dj, em in c.execute("SELECT e.mailbox_id, e.detail_json, r.email FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type='bounce' AND e.event_ts>=?", (от,)):
    x = json.loads(dj or "{}"); dsn = x.get("dsn") or {}
    st = str(dsn.get("status") or x.get("status") or ""); д = str(dsn.get("diagnostic") or x.get("diagnostic") or x.get("error") or "")
    вид = str(dsn.get("kind") or x.get("kind") or x.get("bounce_type") or "")
    if not д: д = str(x.get("snippet") or x.get("text") or "")[:300]
    k = кат(st, д, вид); сч[k] += 1; коды[st or "-"] += 1
    if len(прим[k]) < 3: прим[k].append("%s | %s | %s" % (em, st, re.sub(r"\s+", " ", д)[:150]))
print("ВСЕГО отбивок за 7 дней:", sum(сч.values()))
for k, v in сч.most_common():
    print("\n%4d  %s" % (v, k))
    for p in прим[k]: print("        " + p)
print("\nкоды статуса:", коды.most_common(12))
