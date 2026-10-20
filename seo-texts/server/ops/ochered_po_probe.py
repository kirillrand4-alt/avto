# -*- coding: utf-8 -*-
"""Очередь отправки по пробе (владелец 20.10: «не ясно и отказ пробе сними, без
пробы проверь»).
  1. адреса писем в отправке (scheduled/approved) без вердикта — SMTP-проба
     сейчас же (темп: 3 с между пробами, крупные публичные — раз в 20 с на домен),
     вердикт во все три базы;
  2. письма в отправке, у которых вердикт «неясно», «отказ пробе», «нет ящика»
     или «нет MX», — снимаем с отправки обратно в «Подтвердить отправку»
     (pending_review, карточка pending). Ничего не удаляется: оператор может
     одобрить вручную.
Журнал — _ops/ochered-po-probe.jsonl. Без --primenit — только проба и счёт.
Откат снятия: --otkat."""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
ЖУР = r"C:\sender\_ops\ochered-po-probe.jsonl"
СНЯТЬ = ("неясно", "отказ пробе", "нет ящика", "нет MX")
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.by",
           "yandex.com", "narod.ru", "gmail.com", "rambler.ru", "tut.by", "mail.by"}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
if "--otkat" in sys.argv:
    n = 0
    with c:
        for s in io.open(ЖУР, encoding="utf-8"):
            z = json.loads(s)
            if z.get("что") != "снято":
                continue
            c.execute("UPDATE messages SET status=?, scheduled_at=?, updated_at=? WHERE id=? AND status='pending_review'",
                      (z["bylo"], z["scheduled_at"], т, z["id"]))
            c.execute("UPDATE confirm_reviews SET status='approved', updated_at=? WHERE message_id=? AND status='pending'",
                      (т, z["id"]))
            n += 1
    print("возвращено в отправку:", n)
    sys.exit()

проба_кэш = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ряды = c.execute("SELECT m.id, m.status, m.scheduled_at, lower(r.email), r.inn FROM messages m "
                 "JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','approved')").fetchall()
без = sorted({(r[3], r[4]) for r in ряды if not проба_кэш.get(r[3])})
print("писем в отправке:", len(ряды), "| адресов без пробы:", len(без))
if без:
    from sender.addr_probe import build_addr_probe
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    _п = build_addr_probe(store, cfg)
    проба = getattr(_п, "probe", None) or getattr(_п, "probe_")
    проба.per_domain = 10 ** 6
    посл = {}
    очередь = list(без)
    while очередь:
        отлож = []
        for адрес, инн in очередь:
            дом = адрес.rsplit("@", 1)[-1]
            if дом in КРУПНЫЕ and time.monotonic() - посл.get(дом, -1e9) < 20:
                отлож.append((адрес, инн))
                continue
            посл[дом] = time.monotonic()
            try:
                рез = проба.probe(адрес)
            except Exception as e:  # noqa: BLE001
                рез = {"verdict": "неясно", "answer": str(e)[:200]}
            вер = str(рез.get("verdict") or "неясно")
            проба_кэш[адрес] = вер
            ts = int(time.time())
            try:
                cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
                cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?",
                           (вер, ts, str(рез.get("answer") or "")[:300], адрес))
                cx.commit()
                cx.close()
                ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
                ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
                ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                           "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts",
                           (адрес, вер, "smtp-server", str(рез.get("answer") or "")[:300], ts))
                ox.commit()
                ox.close()
            except Exception as e:  # noqa: BLE001
                print("  в базы не легло:", адрес, str(e)[:80])
            with io.open(ЖУР, "a", encoding="utf-8") as ж:
                ж.write(json.dumps({"что": "проба", "email": адрес, "verdict": вер}, ensure_ascii=False) + "\n")
                ж.flush()
                os.fsync(ж.fileno())
            print("  проба %-40s %s" % (адрес, вер))
            time.sleep(3)
        очередь = отлож
        if очередь:
            time.sleep(5)
сч = Counter(проба_кэш.get(r[3]) or "не проверен" for r in ряды)
print("в отправке по вердиктам:", dict(сч.most_common()))
снять = [r for r in ряды if (проба_кэш.get(r[3]) or "") in СНЯТЬ]
print("к снятию в подтверждение:", len(снять), dict(Counter(проба_кэш.get(r[3]) for r in снять)))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН снятия. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for mid, st, sa, em, _i in снять:
        c.execute("UPDATE messages SET status='pending_review', claimed_at=NULL, updated_at=?, last_error=? "
                  "WHERE id=? AND status IN ('scheduled','approved')", (т, "снято: проба «%s»" % проба_кэш.get(em), mid))
        c.execute("UPDATE confirm_reviews SET status='pending', decided_by=NULL, decided_at=NULL, updated_at=? "
                  "WHERE message_id=? AND status='approved'", (т, mid))
        ж.write(json.dumps({"что": "снято", "id": mid, "bylo": st, "scheduled_at": sa, "email": em,
                            "verdict": проба_кэш.get(em)}, ensure_ascii=False) + "\n")
print("СНЯТО:", len(снять))
