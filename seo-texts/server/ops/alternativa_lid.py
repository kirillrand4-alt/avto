# -*- coding: utf-8 -*-
"""«СМК Альтернатива» прислала техзадание — завести лид и привязать.

Письмо #218976: начальник цеха прислал параметры пневмосистемы, расход 8
куб.м/мин, классы чистоты по ISO 8573-1, перечислил, что стоит сейчас, и
попросил предложения. Тема «компрессор», ветки нет — сторож положил его в
«входящее вне переписки» без получателя, и в ленте лидов его нет.

    python alternativa_lid.py            # показать
    python alternativa_lid.py primenit   # привязать и завести лид
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")

ДЕЛАТЬ = "primenit" in sys.argv[1:]
СОБЫТИЕ = 218976
ОТПРАВИТЕЛЬ = "chernov@smk-alternativa.com"
ДОМЕН = "smk-alternativa.com"
БАЗА = r"C:\sender\sender.db"

c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
print("=== кто это в базе ===")
ряды = c.execute("SELECT id, inn, email, company_name FROM recipients "
                 " WHERE email=? OR lower(domain)=? OR lower(email) LIKE ? "
                 "    OR company_name LIKE '%ЛЬТЕРНАТИВА%'",
                 (ОТПРАВИТЕЛЬ, ДОМЕН, "%@" + ДОМЕН)).fetchall()
for r in ряды:
    print("   #%s %-34s ИНН %-13s %s" % (r["id"], r["email"], r["inn"],
                                         str(r["company_name"])[:40]))
if not ряды:
    print("   в базе нет — писем мы им не отправляли")
ids = [r["id"] for r in ряды]
if ids:
    зн = ",".join("?" * len(ids))
    for m in c.execute("SELECT id, mailbox_id, status, sent_at, subject "
                       "  FROM messages WHERE recipient_id IN (%s) "
                       " ORDER BY id DESC LIMIT 4" % зн, ids):
        print("   письмо #%s %s %s %s | %s" % (m["id"], m["mailbox_id"],
                                               m["status"],
                                               str(m["sent_at"])[:16],
                                               str(m["subject"])[:44]))
    for l in c.execute("SELECT id, reply_kind, status FROM leads "
                       " WHERE recipient_id IN (%s)" % зн, ids):
        print("   лид #%s %s/%s" % (l["id"], l["reply_kind"], l["status"]))

if not ДЕЛАТЬ:
    print("\nвхолостую. Завести — primenit")
    raise SystemExit(0)

e = c.execute("SELECT detail_json FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
d = json.loads(e["detail_json"] or "{}")
текст = " ".join(str(d.get("snippet") or "").split())
# Привязываем к ТОМУ получателю, которому реально писали с этого ящика:
# однофамильцев «Альтернатива» в базе пятеро.
rid = None
for r in ряды:
    if str(r["email"]).endswith("smk-alternativa.ru"):
        rid = r["id"]
        break
rid = rid or (ids[0] if ids else None)
if rid:
    c.execute("UPDATE events SET recipient_id=?, event_type='reply' WHERE id=?",
              (rid, СОБЫТИЕ))
else:
    c.execute("UPDATE events SET event_type='reply' WHERE id=?", (СОБЫТИЕ,))
c.commit()
print("событие переведено в 'reply'%s" % (", получатель #%s" % rid if rid else ""))

from sender.config import Config                              # noqa: E402
from sender.leaddesk import LeadDesk                          # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
десk = LeadDesk(cfg, store)
рек = store.get_recipient(int(rid)) if rid else None
if рек is None:
    # Получателя нет — заводим лид «без компании», как договаривались 25.08:
    # горячее письмо важнее аккуратной привязки.
    from types import SimpleNamespace
    рек = SimpleNamespace(id=None, email=ОТПРАВИТЕЛЬ,
                          company_name='ООО "СМК Альтернатива"', inn=None)
lid = десk.push_warm_lead(
    рек, "", "[hot, тел +7 911 655-04-57] " + текст[:3000], otvetil=ОТПРАВИТЕЛЬ)
print("карточка лида: %s" % lid)
c.close()
