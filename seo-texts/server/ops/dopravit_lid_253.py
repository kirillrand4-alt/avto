# -*- coding: utf-8 -*-
"""Привязать лид 253 к получателю, чтобы в карточке была переписка.

push_warm_lead заводит лид по адресу и не проставляет recipient_id — а блок
«Переписка» строится по нему через store.dialog_thread. Без привязки карточка
показывает «писем и ответов пока нет» и прочерк вместо ИНН.
"""
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ЛИД, ПОЛУЧАТЕЛЬ = 253, 29417
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
r = store.get_recipient(ПОЛУЧАТЕЛЬ)
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
л = c.execute("SELECT id, recipient_id, inn, company_name, email FROM leads "
              " WHERE id=?", (ЛИД,)).fetchone()
print("лид %s: rid=%s инн=%s компания=%s"
      % (л["id"], л["recipient_id"], л["inn"], л["company_name"]))
print("получатель %s: %s | ИНН %s | %s"
      % (ПОЛУЧАТЕЛЬ, getattr(r, "email", "?"), getattr(r, "inn", "?"),
         getattr(r, "company_name", "?")))
n = c.execute("SELECT COUNT(*) FROM events WHERE recipient_id=?",
              (ПОЛУЧАТЕЛЬ,)).fetchone()[0]
print("событий у получателя: %d (их и покажет переписка)" % n)
c.close()
if not КАТИТЬ:
    raise SystemExit(0)
with store.transaction() as conn:
    k = conn.execute(
        "UPDATE leads SET recipient_id=?, inn=?, company_name=?, updated_at=? "
        " WHERE id=? AND recipient_id IS NULL",
        (ПОЛУЧАТЕЛЬ, getattr(r, "inn", None), getattr(r, "company_name", None),
         time.strftime("%Y-%m-%dT%H:%M:%S"), ЛИД)).rowcount
print("привязано: %d" % k)
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
x = c.execute("SELECT recipient_id, inn, company_name FROM leads WHERE id=?",
              (ЛИД,)).fetchone()
print("стало: rid=%s инн=%s %s" % (x["recipient_id"], x["inn"],
                                   str(x["company_name"])[:40]))
c.close()
