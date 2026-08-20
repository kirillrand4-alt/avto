# -*- coding: utf-8 -*-
"""Одобренным карточкам без письма - завести письмо и слот.

Карточки, заведённые imap_watcher (копия на второй адрес), письма не
имеют вовсе: панель отправляла их руками, живой отправкой. Автоотправка
берёт из messages, поэтому одобренная карточка без письма не уедет
никогда - она просто висит одобренной.

Заводим письмо той же кампании и тому же получателю и ставим слот.
Проверяем при этом, что письмо создаётся НОВОЕ: _ensure_message умеет
вернуть уже существующее, и тогда мы бы прицепили карточку к чужому.
"""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.email, cr.campaign_id, cr.recipient_id, cr.status, "
    "       rc.company_name FROM confirm_reviews cr "
    "LEFT JOIN recipients rc ON rc.id=cr.recipient_id "
    "WHERE cr.message_id IS NULL AND cr.status IN ('approved','edited') "
    "ORDER BY cr.id").fetchall()
print(f"одобренных карточек без письма: {len(ряды)}")
for r in ряды:
    print(f"  #{r['id']} {str(r['company_name'])[:30]:<30} {r['email']:<32} "
          f"кампания {r['campaign_id']} получатель {r['recipient_id']}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

сделано = 0
for r in ряды:
    try:
        пара = q._ensure_message(int(r["campaign_id"]), int(r["recipient_id"]))
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} письмо не завелось: {str(ex)[:90]}")
        continue
    mid = пара[0] if пара else None
    if not mid:
        print(f"  #{r['id']} письмо не завелось: {пара}")
        continue
    занято = c.execute("SELECT id FROM confirm_reviews WHERE message_id=? "
                       "AND id<>?", (mid, int(r["id"]))).fetchone()
    if занято:
        print(f"  #{r['id']} письмо {mid} уже принадлежит карточке "
              f"#{занято['id']} - не трогаю")
        continue
    with store._lock:
        store._conn.execute(
            "UPDATE confirm_reviews SET message_id=?, updated_at=? WHERE id=?",
            (int(mid), сейчас.isoformat(), int(r["id"])))
        store._conn.commit()
    rec = store.get_recipient(int(r["recipient_id"]))
    if rec is not None:
        store.reschedule_message(
            int(mid), next_slot(окно, recipient_tz_name(окно, rec), сейчас))
    сделано += 1
    print(f"  #{r['id']} -> письмо {mid}, слот поставлен")
print(f"\nзаведено писем: {сделано}")
