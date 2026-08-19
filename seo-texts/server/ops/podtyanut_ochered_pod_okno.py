# -*- coding: utf-8 -*-
"""Подтянуть очередь автоотправки под ТЕКУЩЕЕ окно.

Зачем. Письмо, которому цикл автоотправки не нашёл часа, откладывается на
next_slot — как правило на завтра 09:00 в зоне получателя. Когда владелец
потом РАСШИРЯЕТ окно, эти письма назад никто не тянет: claim_approved_due
смотрит только scheduled_at, а он уже в завтра. 19.08 так встали 62
мейеровских письма: их подвинули в 11:00 МСК (тогда окно кончалось в 11:00),
через час окно продлили до 15:00 — и очередь всё равно осталась на завтра.

Что делает. Для каждого одобренного письма в 'scheduled' считает next_slot по
ТЕКУЩЕМУ окну и в зоне получателя. Двигает scheduled_at ТОЛЬКО РАНЬШЕ — вперёд
не сдвигает никогда, чтобы не ломать осознанный разгон и не толкать письмо в
закрытый час.

Без --катить — только показывает.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (window_from, next_slot,                  # noqa: E402
                              recipient_tz_name)
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

катить = "--катить" in sys.argv
кампании = [a for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
now = datetime.now(timezone.utc)
win = window_from(store, cfg)

усл = ""
пар: list = []
if кампании:
    усл = f" AND c.campaign_id IN ({','.join('?' * len(кампании))})"
    пар = [int(x) for x in кампании]

with store._lock:
    строки = store._conn.execute(
        "SELECT m.id, m.recipient_id, m.scheduled_at, c.campaign_id "
        "FROM messages m JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE m.status='scheduled'"
        "  AND (SELECT cr.status FROM confirm_reviews cr "
        "       WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) "
        "      IN ('approved','edited')" + усл +
        " ORDER BY m.scheduled_at, m.id", tuple(пар)).fetchall()

print(f"== окно сейчас: {win}")
print(f"== одобрено и ждёт: {len(строки)} писем "
      f"(кампании: {кампании or 'все'})")

итог = Counter()
двигаем: list = []
for r in строки:
    rec = store.get_recipient(r["recipient_id"])
    if rec is None:
        итог["получателя нет в базе"] += 1
        continue
    слот = next_slot(win, recipient_tz_name(win, rec), now)
    было = str(r["scheduled_at"] or "")
    стало = слот.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if стало < было[:19]:
        двигаем.append((int(r["id"]), слот, было, стало,
                        int(r["campaign_id"])))
        итог[f"подтянуть (кампания {r['campaign_id']})"] += 1
    else:
        итог["срок уже правильный"] += 1

for k, v in итог.most_common():
    print(f"  {v:>5}  {k}")

if двигаем:
    print("\n== примеры сдвига ==")
    for mid, _s, было, стало, camp in двигаем[:6]:
        print(f"  #{mid:<6} к{camp}  {было[:16]} -> {стало[:16]}")

if not катить:
    print("\n(сухой прогон — добавь --катить, чтобы применить)")
    sys.exit(0)

сдвинуто = 0
for mid, слот, _b, _s, _c in двигаем:
    try:
        if store.reschedule_message(mid, слот):
            сдвинуто += 1
    except Exception as ex:                                            # noqa: BLE001
        print(f"  #{mid}: не сдвинулось — {str(ex)[:80]}")
print(f"\nПОДТЯНУТО: {сдвинуто} писем из {len(двигаем)}")
