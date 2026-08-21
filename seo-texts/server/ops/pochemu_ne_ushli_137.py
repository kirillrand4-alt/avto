# -*- coding: utf-8 -*-
"""Причины у 137 одобренных писем, которые так и не уехали.

Прежде чем толкать их вручную, надо знать, ПОЧЕМУ они встали. «Уже писали»
толкать нельзя - это дубль. «Нет ящика» или «окно» - можно, это временное.
Мёртвый адрес - нельзя вовсе.
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT cr.id rid, cr.status cst, cr.campaign_id, cr.email, "
        "       m.id mid, m.status mst, COALESCE(m.last_error,'') err, "
        "       substr(m.scheduled_at,1,10) слот, m.attempt_count "
        "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status IN ('approved','edited') AND m.status<>'sent'"
    ).fetchall()
print(f"одобрено, но не ушло: {len(ряды)}\n")


def свернуть(т):
    т = str(т or "").strip()
    т = re.sub(r"\d{4}-\d{2}-\d{2}[T ]?[\d:.]*", "<дата>", т)
    т = re.sub(r"\d{5,}", "<число>", т)
    return т[:96] or "(причина пустая)"


for к, н in Counter(f"{р[5]}: {свернуть(р[6])}" for р in ряды).most_common(20):
    print(f"  {н:>4}  {к}")

print("\nпо слотам:")
for к, н in Counter(str(р[7]) for р in ряды).most_common():
    print(f"  {н:>4}  {к}")

print("\nсегодняшние (слот 21.08) поимённо:")
for р in ряды:
    if str(р[7]) == "2026-08-21":
        print(f"  #{р[0]} камп{р[2]} {р[3]} письмо={р[4]} ({р[5]}) "
              f"попыток={р[8]} :: {свернуть(р[6])}")
