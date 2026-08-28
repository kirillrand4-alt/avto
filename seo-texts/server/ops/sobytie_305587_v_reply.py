# -*- coding: utf-8 -*-
"""Событие 305587 — это ответ, а не «прочее».

Привязка сработала (privyazka=rfc, получатель 29417), текст живой, письмо
пришло на ящик рассылки. Тип 'other' поставлен только потому, что клиент
переслал письмо через веб-интерфейс и почтовик не проставил In-Reply-To.
Из-за типа письмо не попадает в блок «Переписка» карточки лида.

Ключ дедупа не трогаем: он содержит kind='other', и повторный опрос ящика
создаст тот же ключ, то есть дубля не будет.
"""
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, event_type, recipient_id, dedup_key FROM events "
              " WHERE id=305587").fetchone()
print("было: тип=%s получатель=%s ключ=%s"
      % (r["event_type"], r["recipient_id"], r["dedup_key"]))
c.close()
if not КАТИТЬ:
    raise SystemExit(0)
with store.transaction() as conn:
    n = conn.execute("UPDATE events SET event_type='reply' WHERE id=305587 "
                     "  AND event_type='other'").rowcount
print("переклассифицировано: %d" % n)
try:
    т = store.dialog_thread(29417)
    сп = т if isinstance(т, list) else (т.get("items") if isinstance(т, dict) else [])
    print("в переписке теперь записей: %d" % len(сп or []))
    for x in (сп or []):
        if isinstance(x, dict):
            print("   %-4s %s  %s" % (x.get("direction"), str(x.get("ts"))[:16],
                                      str(x.get("body") or x.get("snippet") or "")
                                      .replace("\n", " ")[:90]))
except Exception as ex:
    print("dialog_thread: %s" % str(ex)[:100])
