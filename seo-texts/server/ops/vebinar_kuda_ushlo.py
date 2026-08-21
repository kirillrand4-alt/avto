# -*- coding: utf-8 -*-
"""С каких ящиков реально ушли вебинарные письма и что с полем направления.

В сухом прогоне send_as показывал один и тот же ящик всем: он считает
наименее загруженный на ОДИН момент, до отправки. Реальный ящик выбирается
в момент approve, и вот его и смотрим - вместе с ответом на вопрос, легло
ли letter_division=meyer в карточки.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.status, cr.email, COALESCE(cr.panel_json,'') pj, "
    "       m.id mid, m.status mst, m.mailbox_id, substr(m.sent_at,1,16) когда "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.dedup_key LIKE 'vebinar28:%' ORDER BY cr.id"
).fetchall()
поле = Counter(); статусы = Counter(); ящики = Counter()
for р in ряды:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    поле[str(п.get("letter_division") or "НЕТ")] += 1
    статусы[f"карточка={р['status']} письмо={р['mst'] or '-'}"] += 1
    if р["mst"] == "sent":
        ящики[str(р["mailbox_id"])] += 1
print(f"вебинарных карточек всего: {len(ряды)}")
print("\nполе letter_division:", dict(поле))
print("\nстатусы:")
for к, н in статусы.most_common():
    print(f"  {н:>3}  {к}")
print("\nящики отправки (только ушедшие):")
for к, н in ящики.most_common():
    print(f"  {н:>3}  {к}")
