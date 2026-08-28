# -*- coding: utf-8 -*-
"""Вернуть лид 243 в работу: это не отказ, а приглашение подать КП.

«Для рассмотрения Вашего коммерческого предложения и внесения его в базу
данных, просим заполнить форму обратной связи…» — вход в закупки, а не
отказ. Статус вернём в 'new'.
"""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
десk = LeadDesk(cfg, store)
л = десk.get(243)
print("лид 243: статус %s, тип %s, версия %s"
      % (getattr(л, "status", "?"), getattr(л, "reply_kind", "?"),
         getattr(л, "version", "?")))
try:
    from sender.leaddesk import _VALID_STATUSES, _ПЕРЕХОДЫ  # noqa: F401
    print("допустимые статусы: %s" % sorted(_VALID_STATUSES))
except Exception:
    pass
if not КАТИТЬ:
    raise SystemExit(0)
try:
    об = десk.set_status(243, status="new", user_id=1,
                         note=None)
    print("новый статус: %s" % getattr(об, "status", "?"))
except Exception as ex:
    print("не вышло: %s: %s" % (type(ex).__name__, str(ex)[:160]))
    # переход new<-not_interested может быть запрещён — тогда правим прямо
    with store.transaction() as conn:
        n = conn.execute(
            "UPDATE leads SET status='new', updated_at=? WHERE id=243", 
            (__import__("time").strftime("%Y-%m-%dT%H:%M:%S"),)).rowcount
        conn.execute(
            "INSERT INTO lead_events (lead_id, actor_user_id, action, "
            "  from_status, to_status, detail_json, created_at) "
            " VALUES (?,?,?,?,?,?,?)",
            (243, None, "status_changed", "not_interested", "new",
             '{"pochemu": "не отказ, а приглашение подать КП через форму"}',
             __import__("time").strftime("%Y-%m-%dT%H:%M:%S")))
    print("вернул напрямую: %d" % n)
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT status, updated_at FROM leads WHERE id=243").fetchone()
print("проверка: статус %s, обновлён %s" % (r["status"], str(r["updated_at"])[:19]))
c.close()
