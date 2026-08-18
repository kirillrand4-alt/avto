# -*- coding: utf-8 -*-
"""Дописать message_id письмам очереди, которым его не хватает.

Очередь подтверждения хранит текст, а отправка работает с сообщением: без
строки в messages подтверждение падает «нет message_id — нечего отправлять».
У писем, положенных руками, её не было.

    python zapusk_svoego_skripta.py ops/dodelat_message_dlya_pisma.py 2602 2603 2604
    python zapusk_svoego_skripta.py ops/dodelat_message_dlya_pisma.py 2602 --делать
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ДЕЛАТЬ = "--делать" in sys.argv
ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

for cid in ids:
    with store._lock:
        r = store._conn.execute(
            "SELECT id, campaign_id, recipient_id, message_id, email, status "
            "FROM confirm_reviews WHERE id=?", (cid,)).fetchone()
    if not r:
        print(f"#{cid}: нет такого письма")
        continue
    print(f"#{cid} {r[4]} [{r[5]}] message_id={r[3]}")
    if r[3] or not ДЕЛАТЬ:
        continue
    mid, step, почему = q._ensure_message(int(r[1]), int(r[2]))
    if not mid:
        print(f"  сообщение не завелось: {почему}")
        continue
    with store._lock:
        store._conn.execute(
            "UPDATE confirm_reviews SET message_id=?, updated_at=datetime('now')"
            " WHERE id=?", (mid, cid))
        store._conn.commit()
    print(f"  message_id={mid} (шаг {step})")
