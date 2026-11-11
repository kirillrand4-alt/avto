# -*- coding: utf-8 -*-
"""Владелец 11.11 «эти сними»: из «Подтвердить отправку» — (1) старые напоминания 03–04.11 на РАБОЧИХ
(не на паузе) ящиках, (2) 48 писем «КЦ Россия 9000 10.11», не прошедших заслоны, (3) письмо ФСА от 11.11.
Напоминания на ящике в паузе (p.tyunin) не трогаем. [--primenit]"""
import json, sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); к = st._conn
пауза = {m.mailbox_id for m in cfg.mailboxes() if getattr(st.get_mailbox_state(m.mailbox_id), "paused", False)}
кам = {n: i for i, n in к.execute("SELECT id, name FROM campaigns")}
снять = []
for i, mid, cr, pj in к.execute("SELECT id, message_id, created_at, COALESCE(panel_json,'') FROM confirm_reviews WHERE status='pending' AND kind='reply' AND panel_json LIKE '%napominanie%' AND created_at < '2026-11-09'"):
    if json.loads(pj or "{}").get("mailbox_id") not in пауза | {"p.tyunin@rentgen-control.ru"}: снять.append((i, mid, "старое напоминание 03–04.11"))
for i, mid in к.execute("SELECT id, message_id FROM confirm_reviews WHERE status='pending' AND campaign_id=?", (кам.get("КЦ Россия 9000 10.11"),)):
    снять.append((i, mid, "КЦ Россия 9000: не прошло заслоны"))
for i, mid in к.execute("SELECT id, message_id FROM confirm_reviews WHERE status='pending' AND campaign_id=? AND created_at >= '2026-11-11'", (кам.get("ФСА волна 1 — Meyer"),)):
    снять.append((i, mid, "ФСА 11.11"))
from collections import Counter
print("ящики на паузе:", sorted(пауза))
print("к снятию:", len(снять), dict(Counter(x[2] for x in снять)))
if "--primenit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    with st._lock:
        for i, mid, п in снять:
            к.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", ("владелец 11.11 снять: " + п, т, т, i))
            if mid: к.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='pending_review'", ("снято: " + п, т, mid))
        к.commit()
    print("снято", len(снять))
