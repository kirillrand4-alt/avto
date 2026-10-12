# -*- coding: utf-8 -*-
"""После перезапуска SenderPanel (владелец 12.10: «сделал, письма старые сними»).

1. Кампания 14: снять закрепление за ящиком (scheduled) и вернуть в очередь
   письма, которые перезапуск застал в 'sending' (Яндекс лежит — они не
   ушли; панель сама такие не возвращает).
2. Кампания 11: снять 18 одобренных писем, висящих в 'sending' с 1–10
   сентября (решение владельца — «сними»): статус skipped, причина в ошибке.

Запуск: posle_perezapuska.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time

ПРИМЕНИТЬ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
now = time.strftime("%Y-%m-%dT%H:%M:%S")
print("время сервера: %s" % now)

к14 = [dict(р) for р in c.execute(
    "SELECT id, status, mailbox_id, claimed_at FROM messages "
    "WHERE campaign_id=14 AND status IN ('scheduled','sending')")]
откр = [р["id"] for р in к14 if р["mailbox_id"] and р["status"] == "scheduled"]
# В 'sending' возвращаем только СИРОТ: взятых больше 15 минут назад. Свежие
# может держать текущий проход нового процесса — он вернёт их сам.
from datetime import datetime, timedelta  # noqa: E402
порог = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
зав14 = [р["id"] for р in к14 if р["status"] == "sending"
         and str(р["claimed_at"] or "") < порог]
свежие14 = [р["id"] for р in к14 if р["status"] == "sending"
            and str(р["claimed_at"] or "") >= порог]
к11 = [dict(р) for р in c.execute(
    "SELECT id, claimed_at, attempt_count FROM messages "
    "WHERE campaign_id=11 AND status='sending'")]
print("кампания 14: в очереди с закреплением %d, в 'sending' сирот %d, "
      "свежих (в работе прохода) %d" % (len(откр), len(зав14), len(свежие14)))
for р in к14:
    if р["status"] == "sending":
        print("   sending #%s claimed %s" % (р["id"], р["claimed_at"]))
print("кампания 11: в 'sending' %d (claimed %s … %s)"
      % (len(к11), min((р["claimed_at"] or "") for р in к11) if к11 else "-",
         max((р["claimed_at"] or "") for р in к11) if к11 else "-"))
if ПРИМЕНИТЬ:
    with c:
        if откр:
            c.execute("UPDATE messages SET mailbox_id=NULL, updated_at=? "
                      "WHERE id IN (%s) AND status='scheduled'"
                      % ",".join(map(str, откр)), (now,))
        if зав14:
            c.execute("UPDATE messages SET status='scheduled', claimed_at=NULL, "
                      "mailbox_id=NULL, updated_at=? WHERE id IN (%s) "
                      "AND status='sending'" % ",".join(map(str, зав14)), (now,))
        if к11:
            c.execute("UPDATE messages SET status='skipped', claimed_at=NULL, "
                      "last_error=?, updated_at=? WHERE id IN (%s) "
                      "AND status='sending'" % ",".join(str(р["id"]) for р in к11),
                      ("снято владельцем 12.10: висело в sending с сентября", now))
    with io.open(r"C:\sender\_ops\posle-perezapuska.jsonl", "a",
                 encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": now, "14_otkrepleno": откр,
                            "14_iz_sending": зав14,
                            "11_snyato": [р["id"] for р in к11]},
                           ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
итог = {р[0]: р[1] for р in c.execute(
    "SELECT status || ' ' || COALESCE(mailbox_id,'(без ящика)'), COUNT(*) "
    "FROM messages WHERE campaign_id=14 AND status IN ('scheduled','sending') "
    "GROUP BY 1")}
print("кампания 14 сейчас: %s" % итог)
print("кампания 11 в 'sending': %d" % c.execute(
    "SELECT COUNT(*) FROM messages WHERE campaign_id=11 AND status='sending'"
).fetchone()[0])
print("=== ПОСЛЕ ПЕРЕЗАПУСКА: %s ===" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
