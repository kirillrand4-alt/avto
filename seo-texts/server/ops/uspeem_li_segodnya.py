# -*- coding: utf-8 -*-
"""Слот есть у всех — но успеет ли очередь уйти в сегодняшнее окно.

Считаем не теорию, а факт: сколько ушло по часам сегодня, сколько окна
осталось, и какой потолок дают ящики (рампа минус уже отправленное).
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
сейчас = datetime.now(timezone.utc)
окно = json.loads(c.execute(
    "SELECT value FROM panel_settings WHERE key='sending_window'").fetchone()[0])
print("сервер сейчас: %s UTC (МСК %s)"
      % (сейчас.strftime("%d.%m %H:%M"),
         (сейчас + timedelta(hours=3)).strftime("%H:%M")))
print("окно: %s-%s %s" % (окно.get("start"), окно.get("end"), окно.get("tz")))

срок = c.execute(
    "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending') "
    "  AND scheduled_at <= ?", (сейчас.isoformat(),)).fetchone()[0]
всего = c.execute("SELECT COUNT(*) FROM messages "
                  " WHERE status IN ('scheduled','sending')").fetchone()[0]
print("\nв очереди %d, из них срок уже настал: %d" % (всего, срок))
print("ближайшие и дальние слоты:")
for р in c.execute("SELECT MIN(scheduled_at) a, MAX(scheduled_at) b FROM messages "
                   " WHERE status IN ('scheduled','sending')"):
    print("   от %s до %s" % (р["a"], р["b"]))

print("\n=== УШЛО СЕГОДНЯ ПО ЧАСАМ (UTC) ===")
всего_сег = 0
for р in c.execute("SELECT substr(sent_at,12,2) ч, COUNT(*) n FROM messages "
                   " WHERE status='sent' AND substr(sent_at,1,10)=date('now') "
                   " GROUP BY ч ORDER BY ч"):
    всего_сег += р["n"]
    print("   %s:00 UTC (%02d МСК)  %4d" % (р["ч"], (int(р["ч"]) + 3) % 24, р["n"]))
print("   итого сегодня: %d" % всего_сег)

print("\n=== ПОТОЛОК ЯЩИКОВ НА СЕГОДНЯ ===")
КРИВАЯ = [3, 5, 8, 12, 18, 25, 32, 40, 50]
запас = 0
живых = 0
for р in c.execute("SELECT mailbox_id, ramp_day, sent_today, paused "
                   "  FROM mailbox_state ORDER BY mailbox_id"):
    лимит = КРИВАЯ[min(int(р["ramp_day"]), len(КРИВАЯ) - 1)]
    ост = max(0, лимит - int(р["sent_today"]))
    if р["paused"]:
        ост = 0
    else:
        живых += 1
    запас += ост
    print("   %-38s лимит %3d отправлено %3d осталось %3d%s"
          % (р["mailbox_id"], лимит, р["sent_today"], ост,
             "  ПАУЗА" if р["paused"] else ""))
print("   живых ящиков %d, суммарный запас на сегодня: %d писем" % (живых, запас))

шаг = 255.0  # средний интервал пейсинга 90..420 сек
осталось_мин = 0
try:
    from zoneinfo import ZoneInfo
    мск = сейчас.astimezone(ZoneInfo(str(окно.get("tz") or "Europe/Moscow")))
    ч, м = [int(x) for x in str(окно.get("end", "12:00")).split(":")[:2]]
    конец = мск.replace(hour=ч, minute=м, second=0, microsecond=0)
    осталось_мин = max(0.0, (конец - мск).total_seconds() / 60.0)
except Exception as e:  # noqa: BLE001
    print("окно не посчиталось: %s" % e)
темп = живых * 60.0 / шаг
print("\nдо конца окна %.0f мин, темп ~%.1f писем/мин на %d ящиках"
      % (осталось_мин, темп, живых))
print("физически успеет ещё ~%d писем, а с учётом лимитов ящиков ~%d"
      % (осталось_мин * темп, min(осталось_мин * темп, запас)))
