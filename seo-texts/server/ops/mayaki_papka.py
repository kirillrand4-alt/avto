# -*- coding: utf-8 -*-
"""Что маяки говорят про папку: входящие или спам, и есть ли замеры по дням."""
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) FROM events WHERE event_type='mayak'").fetchone()[0]
print("событий 'mayak' в журнале: %d" % n)
for r in c.execute("SELECT id, event_ts, mailbox_id, detail_json FROM events "
                   " WHERE event_type='mayak' ORDER BY event_ts DESC LIMIT 20"):
    d = {}
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        pass
    print("  %s ящик=%-34s %s" % (str(r["event_ts"])[:19],
                                  str(r["mailbox_id"])[:34],
                                  json.dumps(d, ensure_ascii=False)[:180]))
з = c.execute("SELECT value FROM panel_settings WHERE key='mayaki_kampaniya'"
              ).fetchone()
print("\nслужебная кампания маяков: %s" % (з["value"] if з else "не заведена"))
c.close()
print("\nнастройки маяков в конфиге:")
try:
    from sender.config import Config
    from sender import mayaki as M
    cfg = Config.load(r"C:\sender\sender.yaml")
    for имя in ("nastroyki", "spisok", "mayaki"):
        f = getattr(M, имя, None)
        if callable(f):
            try:
                print("  %s() -> %s" % (имя, str(f(cfg))[:400]))
            except Exception as ex:
                print("  %s(): %s" % (имя, ex))
except Exception as ex:
    print("  не прочитать: %s" % ex)
