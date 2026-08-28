# -*- coding: utf-8 -*-
"""Отбивка в карточке лида «ИМПЭКС-ДОН»: посмотреть и убрать из переписки.

Владелец: «вот это сообщение удали, а то когда буду слать продажникам лид они
нифига не поймут». Событие 'bounce' кормит гейты и kill-switch (bounce_rate
считается по event_type='bounce'), поэтому УДАЛЯТЬ строку из events нельзя —
поменяем тип на 'bounce_skryt': из ленты диалога исчезнет (store.dialog_thread
берёт reply/reply_auto/complaint/dsn/bounce), а сама запись останется, и в
detail_json проставим пометку, кто и зачем спрятал.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПОЛУЧАТЕЛЬ = 29417
БАЗА = r"C:\sender\sender.db"

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, email, inn, company_name FROM recipients WHERE id=?",
              (ПОЛУЧАТЕЛЬ,)).fetchone()
print("получатель %s: %s | ИНН %s | %s"
      % (r["id"], r["email"], r["inn"], str(r["company_name"])[:50]))
print("--- все получатели этого ИНН ---")
for x in c.execute("SELECT id, email FROM recipients WHERE inn=? ORDER BY id",
                   (r["inn"],)):
    print("  rid=%s %s" % (x["id"], x["email"]))
print("--- события получателя %s ---" % ПОЛУЧАТЕЛЬ)
for e in c.execute("SELECT id, event_type, event_ts, mailbox_id, detail_json "
                   "  FROM events WHERE recipient_id=? ORDER BY event_ts",
                   (ПОЛУЧАТЕЛЬ,)):
    d = {}
    try:
        d = json.loads(e["detail_json"] or "{}")
    except Exception:
        pass
    сн = str(d.get("snippet") or d.get("subject") or "").replace("\n", " ")
    print("  ev=%s %s %s ящик=%s :: %s"
          % (e["id"], e["event_type"], e["event_ts"], e["mailbox_id"], сн[:150]))
print("--- отправленные письма ---")
for m in c.execute("SELECT id, sent_at, status, mailbox_id, subject "
                   "  FROM messages WHERE recipient_id=? ORDER BY id",
                   (ПОЛУЧАТЕЛЬ,)):
    print("  msg=%s %s %s ящик=%s :: %s"
          % (m["id"], m["sent_at"], m["status"], m["mailbox_id"],
             str(m["subject"])[:70]))
c.close()

print("--- лента диалога СЕЙЧАС ---")
for it in store.dialog_thread(ПОЛУЧАТЕЛЬ):
    print("  %s %s [%s] %s :: %s"
          % (it.get("direction"), it.get("ts"), it.get("kind"),
             str(it.get("subject"))[:50],
             str(it.get("body") or "").replace("\n", " ")[:120]))

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit спрячу отбивки из ленты")
    raise SystemExit(0)

with store.transaction() as conn:
    строки = conn.execute(
        "SELECT id, detail_json FROM events "
        " WHERE recipient_id=? AND event_type IN ('bounce','dsn')",
        (ПОЛУЧАТЕЛЬ,)).fetchall()
    сп = 0
    for s in строки:
        try:
            d = json.loads(s["detail_json"] or "{}")
        except Exception:
            d = {}
        if not isinstance(d, dict):
            d = {}
        d["skryto_iz_lenty"] = {
            "kogda": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pochemu": "лид уходит в отдел продаж, отбивка по мёртвому адресу "
                       "путает продажника; запись сохранена для гейтов",
        }
        conn.execute("UPDATE events SET event_type='bounce_skryt', "
                     "       detail_json=? WHERE id=?",
                     (json.dumps(d, ensure_ascii=False), s["id"]))
        сп += 1
print("спрятано событий: %d" % сп)

print("--- лента диалога ПОСЛЕ ---")
for it in store.dialog_thread(ПОЛУЧАТЕЛЬ):
    print("  %s %s [%s] %s :: %s"
          % (it.get("direction"), it.get("ts"), it.get("kind"),
             str(it.get("subject"))[:50],
             str(it.get("body") or "").replace("\n", " ")[:120]))
