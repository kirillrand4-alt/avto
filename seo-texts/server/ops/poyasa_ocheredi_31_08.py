# -*- coding: utf-8 -*-
"""Только чтение: часовые пояса получателей очереди и попадание в окно."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ПОЯСА ПОЛУЧАТЕЛЕЙ В ОЧЕРЕДИ ===")
c = Counter()
for р in s.execute("SELECT COALESCE(r.tz,'(пусто)') tz, COUNT(*) n"
                   " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.status='scheduled' GROUP BY tz ORDER BY n DESC"):
    c[р["tz"]] = р["n"]
    print("  %-28s %4d" % (р["tz"], р["n"]))

print("\n=== ПОПАДАЕТ ЛИ СЕЙЧАС В ОКНО 09:00-14:00 ПО ПОЯСУ ПОЛУЧАТЕЛЯ ===")
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
сейчас = datetime.now(timezone.utc)
успеет = мимо = неясно = 0
подробно = Counter()
for tz, n in c.items():
    if ZoneInfo is None or tz in ("(пусто)", "None", ""):
        неясно += n
        подробно["пояс не задан -> берётся Europe/Moscow"] += n
        continue
    try:
        мест = сейчас.astimezone(ZoneInfo(tz))
    except Exception:
        неясно += n
        подробно["пояс не разобрался: %s" % tz] += n
        continue
    ч = мест.hour + мест.minute / 60.0
    буд = мест.isoweekday() in (1, 2, 3, 4, 5)
    if not буд:
        мимо += n
        подробно["выходной в поясе %s" % tz] += n
    elif ч >= 14:
        мимо += n
        подробно["окно на сегодня закрыто (%s, %02d:%02d)" % (tz, мест.hour, мест.minute)] += n
    else:
        успеет += n
        подробно["успевает (%s, сейчас %02d:%02d)" % (tz, мест.hour, мест.minute)] += n

for k, v in подробно.most_common(14):
    print("  %-52s %4d" % (k, v))

print("\n=== ИТОГ ===")
print("  всего в очереди: %d" % sum(c.values()))
print("  успевают в сегодняшнее окно по своему поясу: %d" % успеет)
print("  окно на сегодня уже закрыто / выходной      : %d" % мимо)
print("  пояс не задан (пойдут по московскому)       : %d" % неясно)
print("  сейчас UTC %s, МСК %s"
      % (сейчас.strftime("%H:%M"),
         сейчас.astimezone(ZoneInfo("Europe/Moscow")).strftime("%H:%M") if ZoneInfo else "?"))
