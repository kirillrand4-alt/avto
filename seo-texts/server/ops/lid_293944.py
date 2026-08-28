# -*- coding: utf-8 -*-
import json, sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
e = c.execute("SELECT detail_json FROM events WHERE id=293944").fetchone()
r = c.execute("SELECT email FROM recipients WHERE id=30282").fetchone()
c.close()
d = json.loads(e["detail_json"] or "{}")
десk = LeadDesk(cfg, store)
try:
    ок = десk.push_warm_lead(
        r["email"], None,
        "[redirect] %s" % str(d.get("snippet") or "")[:400],
        otvetil="dmg@virtex-food.ru")
    print("push_warm_lead -> %r" % (ок,))
except Exception as ex:
    print("push_warm_lead упал: %s: %s" % (type(ex).__name__, str(ex)[:160]))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
l = c.execute("SELECT id, status, email, reply_kind FROM leads "
              " WHERE recipient_id=30282 OR email='sales-p@virtex-food.ru'").fetchone()
print("лид: %s" % (dict(l) if l else "нет"))
c.close()
