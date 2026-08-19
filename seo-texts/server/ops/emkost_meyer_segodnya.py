# -*- coding: utf-8 -*-
"""Сколько мейеровских писем ещё влезет сегодня: лимиты ящиков и темп.

Вопрос владельца прямой: перекинул ли я мейер на отправку и уедет ли он.
Отвечаем цифрами: что ушло, что ждёт, сколько ящик может ещё сегодня и с
какой скоростью очередь тает.
"""
import sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.ramp import curve_value                                    # noqa: E402
from sender.store import Store                                         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
now = datetime.now(timezone.utc)
МСК = ZoneInfo("Europe/Moscow")
print(f"== {now.astimezone(МСК).strftime('%H:%M')} МСК, окно до 15:00 ==")

for камп, имя in ((11, "Meyer"), (10, "КЦ")):
    with store._lock:
        ушло = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE c.campaign_id=? AND m.status='sent' "
            "AND date(m.sent_at)=date('now')", (камп,)).fetchone()[0]
        ждёт = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE c.campaign_id=? "
            "AND m.status='scheduled' AND m.scheduled_at<=? "
            "AND (SELECT cr.status FROM confirm_reviews cr "
            "     WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) "
            "    IN ('approved','edited')",
            (камп, now.strftime("%Y-%m-%dT%H:%M:%S"))).fetchone()[0]
    print(f"  {имя:<6} ушло сегодня {ушло:>4} | созрело и ждёт {ждёт:>4}")

print("\n== ящики: сколько ещё можно сегодня ==")
всего_осталось = Counter()
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    напр = "Meyer" if ("meyer" in div or "мейер" in div) else "КЦ"
    st = store.get_mailbox_state(mb.mailbox_id)
    сег = getattr(st, "sent_today", 0) if st else 0
    рд = getattr(st, "ramp_day", 0) if st else 0
    посл = getattr(st, "last_sent_at", None) if st else None
    try:
        лим = int(curve_value(cfg.ramp_curve(mb.provider), рд))
    except Exception:                                                  # noqa: BLE001
        лим = -1
    ост = max(0, лим - сег) if лим >= 0 else -1
    if напр == "Meyer":
        всего_осталось["Meyer"] += max(0, ост)
        пауза = getattr(st, "paused", False) if st else False
        print(f"  {mb.mailbox_id:<38} рамп{рд:>3}  {сег:>3}/{лим:<3} "
              f"осталось {ост:>3}  пауза={пауза}  посл={str(посл)[11:16]}")
    else:
        всего_осталось["КЦ"] += max(0, ост)

print(f"\n  ЁМКОСТЬ ДО КОНЦА ДНЯ: Meyer {всего_осталось['Meyer']}, "
      f"КЦ {всего_осталось['КЦ']}")

print("\n== темп за последний час (все кампании) ==")
with store._lock:
    темп = store._conn.execute(
        "SELECT substr(sent_at,12,2) AS ч, COUNT(*) FROM messages "
        "WHERE status='sent' AND date(sent_at)=date('now') "
        "GROUP BY ч ORDER BY ч").fetchall()
for ч, n in темп:
    мск = (int(ч) + 3) % 24
    print(f"  {ч}:00 UTC (= {мск:02d}:00 МСК): {n}")
