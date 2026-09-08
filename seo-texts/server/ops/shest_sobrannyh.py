# -*- coding: utf-8 -*-
"""Шесть писем партии, у которых тело уже собрано: что это за письма."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
НОВЫЙ = "решето и аспирация"
store = Store(r"C:\sender\sender.db")
with store._lock:
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.status AS cst, c.email, c.recipient_id,
                  m.id AS mid, m.status AS mst, m.subject AS msub,
                  m.sent_at, m.created_at, m.campaign_id, m.body_rendered
             FROM confirm_reviews c JOIN messages m ON c.message_id = m.id
            WHERE c.subject=?""", (ТЕМА,)).fetchall()
for р in строки:
    т = str(р["body_rendered"] or "")
    if not т.strip() or НОВЫЙ in т:
        continue
    print("=" * 72)
    print("карточка %s (%s) %s" % (р["cid"], р["cst"], р["email"]))
    print("письмо %s (%s) кампания %s | создано %s | отправлено %s"
          % (р["mid"], р["mst"], р["campaign_id"], р["created_at"],
             р["sent_at"]))
    print("тема письма: %s" % str(р["msub"])[:70])
    print("наша тема:   %s" % ТЕМА)
    print("тело письма (начало): %s" % " ".join(т.split())[:160])
print("")
print("=" * 72)
print("=== ИТОГ: сколько карточек партии смотрит на чужое письмо ===")
n = sum(1 for р in строки if str(р["body_rendered"] or "").strip()
        and НОВЫЙ not in str(р["body_rendered"] or ""))
print("таких карточек: %d из %d" % (n, len(строки)))
