# -*- coding: utf-8 -*-
"""Ответы людей, которых НЕТ в ленте лидов (владелец 20.10: «посмотри такие и
подобные в ящиках, если нет в ленте — заведи в ленту»).

Берём события reply (без автоответов) за N дней (по умолч. 30). Лид считается
заведённым, если в leads есть строка по тому же получателю, адресу ответившего
или ИНН. Ответ без получателя (не привязался к письму) привязываем по адресу
ответившего, затем по домену к компании, которой мы писали с этого же ящика.
С --zavesti — штатный LeadDesk.push_warm_lead (без проброса в Битрикс),
статус «new». Журнал — _ops/otvety-bez-lenty.jsonl.

    otvety_bez_lenty.py [N] [--zavesti]"""
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\sender")
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))
от = (datetime.utcnow() - timedelta(days=N)).strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
лид_rid = {r[0] for r in c.execute("SELECT recipient_id FROM leads WHERE recipient_id IS NOT NULL")}
лид_адр = {str(r[0]).lower() for r in c.execute("SELECT email FROM leads WHERE email IS NOT NULL")}
лид_инн = {str(r[0]) for r in c.execute("SELECT inn FROM leads WHERE inn IS NOT NULL AND inn!=''")}
нет = []
пример = None
for ev in c.execute("SELECT * FROM events WHERE event_type='reply' AND event_ts>=? ORDER BY event_ts", (от,)).fetchall():
    d = json.loads(ev["detail_json"] or "{}")
    пример = пример or d
    от_кого = str(d.get("from") or d.get("from_email") or d.get("sender") or "").lower()
    if "<" in от_кого:
        от_кого = от_кого.split("<")[-1].rstrip(">").strip()
    rid = ev["recipient_id"]
    rec = c.execute("SELECT * FROM recipients WHERE id=?", (rid,)).fetchone() if rid else None
    if rec is None and от_кого:
        rec = c.execute("SELECT * FROM recipients WHERE lower(email)=?", (от_кого,)).fetchone()
    if rec is None and "@" in от_кого:
        дом = от_кого.split("@")[-1]
        rec = c.execute("SELECT r.* FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' "
                        "AND r.domain=? AND m.mailbox_id=? ORDER BY m.sent_at DESC LIMIT 1", (дом, ev["mailbox_id"])).fetchone()
    inn = str(rec["inn"]) if rec is not None and rec["inn"] else ""
    if (rec is not None and rec["id"] in лид_rid) or от_кого in лид_адр or (inn and inn in лид_инн):
        continue
    нет.append({"event_id": ev["id"], "ts": ev["event_ts"], "ящик": ev["mailbox_id"], "от": от_кого,
                "rid": rec["id"] if rec is not None else None, "компания": rec["company_name"] if rec is not None else None,
                "inn": inn, "тема": str(d.get("subject") or "")[:80],
                "текст": str(d.get("snippet") or d.get("text") or d.get("body") or "")[:300],
                "thread": d.get("thread_id") or d.get("message_id") or d.get("in_reply_to") or ("ev%s" % ev["id"])})
print("ключи detail_json ответа:", sorted((пример or {}).keys()))
print("ответов людей за %d дней без лида в ленте: %d" % (N, len(нет)))
for x in нет:
    print("  %s | %-38s | от %-34s | %s | %s" % (x["ts"][:16], x["ящик"], x["от"], (x["компания"] or "НЕ ПРИВЯЗАН")[:30], x["текст"][:90].replace("\n", " ")))
if "--zavesti" not in sys.argv:
    print("СУХОЙ ПРОГОН. Завести в ленту — --zavesti")
    sys.exit()
from sender.config import Config        # noqa: E402
from sender.leaddesk import LeadDesk     # noqa: E402
from sender.store import Store          # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
ld = LeadDesk(cfg, store)
ж = io.open(r"C:\sender\_ops\otvety-bez-lenty.jsonl", "a", encoding="utf-8")
n = 0
for x in нет:
    if not x["rid"]:
        print("  пропуск (не к кому привязать):", x["от"])
        continue
    rec = store.get_recipient(int(x["rid"]))
    lid = ld.push_warm_lead(rec, str(x["thread"]), x["текст"], otvetil=x["от"] or None, v_bitrix=False)
    ж.write(json.dumps(dict(x, lead_id=lid), ensure_ascii=False) + "\n")
    n += 1
    print("  лид #%s: %s (%s)" % (lid, x["от"], x["компания"]))
ж.flush()
os.fsync(ж.fileno())
print("заведено:", n)
