# -*- coding: utf-8 -*-
"""Весь разговор с компанией по времени: наши письма, их ответы, наши ответы.

Аргумент — recipient_id или кусок почты. Показывает и messages, и events,
слитые в одну ленту: только так видно, ушёл ли наш ответ и был ли встречный.
"""
import json
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

ключ = sys.argv[1]
ПОЛНЫЙ = "--полный" in sys.argv or "--full" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def _текст(s, лимит=1200):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;?", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s if ПОЛНЫЙ else s[:лимит]


with store._lock:
    if ключ.isdigit():
        rec = store._conn.execute(
            "SELECT * FROM recipients WHERE id=?", (int(ключ),)).fetchone()
    else:
        rec = store._conn.execute(
            "SELECT * FROM recipients WHERE email LIKE ?",
            (f"%{ключ}%",)).fetchone()
if rec is None:
    print("получателя не нашёл"); raise SystemExit(1)
rid = int(rec["id"])
print(f"== {rec['company_name']} <{rec['email']}> (recipient_id={rid}, "
      f"ИНН {rec['inn']}) ==")

лента = []
with store._lock:
    пис = store._conn.execute(
        "SELECT id, status, mailbox_id, sent_at, scheduled_at, subject, "
        "       body_rendered, rfc_message_id, in_reply_to, campaign_id "
        "FROM messages WHERE recipient_id=? ORDER BY COALESCE(sent_at, "
        "scheduled_at, created_at)", (rid,)).fetchall()
    соб = store._conn.execute(
        "SELECT id, event_type, event_ts, mailbox_id, detail_json "
        "FROM events WHERE recipient_id=? ORDER BY event_ts", (rid,)).fetchall()
    лиды = store._conn.execute(
        "SELECT id, status, reply_kind, phone, need, assigned_to, created_at "
        "FROM leads WHERE recipient_id=? ORDER BY created_at", (rid,)).fetchall()

for m in пис:
    когда = m["sent_at"] or m["scheduled_at"] or ""
    лента.append((str(когда), "ПИСЬМО", dict(m)))
for e in соб:
    лента.append((str(e["event_ts"] or ""), "СОБЫТИЕ", dict(e)))
лента.sort(key=lambda t: t[0])

for когда, вид, д in лента:
    if вид == "ПИСЬМО":
        напр = "-> НАШЕ" if д["status"] == "sent" else f"   [{д['status']}]"
        print(f"\n{когда[:16]}  {напр}  #{д['id']} к{д['campaign_id']} "
              f"с {д['mailbox_id'] or '—'}")
        print(f"    тема: {д['subject']}")
        т = _текст(д["body_rendered"])
        for л in т.split("\n")[:14 if not ПОЛНЫЙ else 999]:
            if л.strip():
                print(f"    | {л.strip()[:150]}")
    else:
        d = {}
        try:
            d = json.loads(д["detail_json"] or "{}")
        except Exception:                                              # noqa: BLE001
            pass
        тело = _текст(d.get("body") or d.get("text") or d.get("snippet") or "")
        стрелка = ("<- ОТ НИХ" if д["event_type"] in ("reply", "reply_auto")
                   else "   ")
        print(f"\n{когда[:16]}  {стрелка}  событие {д['event_type']}"
              + (f"  ящик {д['mailbox_id']}" if д["mailbox_id"] else ""))
        if d.get("subject"):
            print(f"    тема: {_текст(d['subject'], 120)}")
        for л in тело.split("\n")[:14 if not ПОЛНЫЙ else 999]:
            if л.strip():
                print(f"    | {л.strip()[:150]}")

print("\n== карточки лида ==")
for l in лиды:
    print(f"  лид #{l['id']} {l['created_at'][:16]} статус={l['status']} "
          f"тип={l['reply_kind']} телефон={l['phone']} "
          f"назначен={l['assigned_to']}")
    if l["need"]:
        print(f"    потребность: {_текст(l['need'], 300)}")
