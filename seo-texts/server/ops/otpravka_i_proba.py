# -*- coding: utf-8 -*-
"""Прошло ли пробу то, что уходит (владелец 20.10). За последние N суток (по умолч. 2):
отправленные по кампаниям x вердикт пробы адреса (и был ли вердикт ДО отправки),
отбивки x вердикт, и что стоит в отправке сейчас x вердикт. Только чтение.
    otpravka_i_proba.py [N]"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
от = (datetime.utcnow() - timedelta(days=N)).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
кол = {r[1] for r in c.execute("PRAGMA table_info(addr_probe)")}
кол_ts = next((k for k in ("ts", "checked_at", "updated_at", "probed_at") if k in кол), None)
проба = {}
for r in c.execute("SELECT email, verdict%s FROM addr_probe" % ((", " + кол_ts) if кол_ts else "")):
    проба[str(r[0]).lower()] = (str(r[1] or ""), str(r[2]) if кол_ts else "")


def вердикт(em, когда=None):
    v, ts = проба.get(str(em or "").lower(), ("", ""))
    if not v:
        return "не проверен"
    if когда and ts and ts[:19].replace("T", " ") > str(когда)[:19].replace("T", " "):
        return v + " (проба ПОСЛЕ отправки)"
    return v


print("с", от, "| колонка времени пробы:", кол_ts)
отпр = defaultdict(Counter)
for cid, em, sa in c.execute("SELECT m.campaign_id, r.email, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                             "WHERE m.status='sent' AND m.sent_at>=?", (от,)):
    отпр[кам.get(cid, cid)][вердикт(em, sa)] += 1
print("\nОТПРАВЛЕНО по кампаниям x вердикт пробы:")
for k, v in sorted(отпр.items(), key=lambda x: -sum(x[1].values())):
    print("  %-30s %4d  %s" % (str(k)[:30], sum(v.values()), dict(v.most_common())))
сч = Counter()
кат = Counter()
for dj, em, ts in c.execute("SELECT e.detail_json, r.email, e.event_ts FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
                            "WHERE e.event_type IN ('bounce','failed') AND e.event_ts>=?", (от,)):
    d = json.loads(dj or "{}")
    диаг = str((d.get("dsn") or {}).get("diagnostic") or d.get("error") or "")
    к = ("спам" if re.search(r"(?i)spam|спам|5\.7\.1", диаг) else
         "нет ящика" if re.search(r"(?i)no such|unknown|not exist|не существ|5\.1\.1|mailbox unavailable|недоступ", диаг) else
         "переполнен" if re.search(r"(?i)quota|full|переполн|5\.2\.2", диаг) else
         "политика" if re.search(r"(?i)relay|policy|not permitted|blocked|reject", диаг) else "прочее")
    сч[(к, вердикт(em))] += 1
    кат[к] += 1
print("\nОТБИВКИ: всего %d, по видам %s" % (sum(сч.values()), dict(кат.most_common())))
for k, v in сч.most_common(15):
    print("  %3d  %-12s вердикт пробы: %s" % (v, k[0], k[1]))
оч = defaultdict(Counter)
for cid, st, em in c.execute("SELECT m.campaign_id, m.status, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                             "WHERE m.status IN ('scheduled','approved','sending')"):
    оч[(кам.get(cid, cid), st)][вердикт(em)] += 1
print("\nСЕЙЧАС В ОТПРАВКЕ x вердикт:")
for k, v in sorted(оч.items(), key=lambda x: -sum(x[1].values())):
    print("  %-30s %-9s %4d  %s" % (str(k[0])[:30], k[1], sum(v.values()), dict(v.most_common())))
