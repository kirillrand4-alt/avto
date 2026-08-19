# -*- coding: utf-8 -*-
"""Сколько писем С УПОМИНАНИЕМ КЕЙСОВ реально стоит на отправку.

Я сказал владельцу «266 одобренных писем в очереди» — это была ошибка:
266 это все написанные письма, где встречается упоминание, включая давно
отправленные, снятые и не решённые. Очередь на отправку — это одобренная
карточка, чьё письмо ещё в 'scheduled'.
"""
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _ОПУБЛИКОВАННЫЕ_КЕЙСЫ as RX          # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        ждут = store._conn.execute(
            "SELECT c.id, c.email, c.body FROM confirm_reviews c "
            "JOIN messages m ON m.id=c.message_id "
            "WHERE c.campaign_id=? AND c.status IN ('approved','edited') "
            "AND m.status='scheduled'", (камп,)).fetchall()
        ушло = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews c "
            "JOIN messages m ON m.id=c.message_id "
            "WHERE c.campaign_id=? AND m.status='sent'", (камп,)).fetchone()[0]
    с_кейсами = []
    for r in ждут:
        тело = re.sub(r"<[^>]+>", " ", str(r["body"] or ""))
        м = RX.search(тело)
        if м:
            с_кейсами.append((r["id"], r["email"], м.group(0)[:60]))
    print(f"\n== {имя} ==")
    print(f"  ждут отправки: {len(ждут)}")
    print(f"  из них с упоминанием кейсов: {len(с_кейсами)}")
    print(f"  уже отправлено (для справки): {ушло}")
    for i, e, ф in с_кейсами[:10]:
        print(f"    #{i} {e} — «{ф}»")
