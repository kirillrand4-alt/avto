# -*- coding: utf-8 -*-
"""Когда и с какой скоростью уйдёт партия: окна по зонам и ёмкость ящиков."""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
from sender.auto_send import window_from                        # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True)
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)

# 1. сколько писем партии в каждой зоне
зоны = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT r.tz, COUNT(*) c FROM confirm_reviews cr
                 JOIN recipients r ON cr.recipient_id = r.id
                WHERE cr.subject=? AND cr.status IN ('pending','approved')
             GROUP BY r.tz""", (ТЕМА,)):
        зоны[str(р["tz"] or "нет")] = int(р["c"])

def сдвиг(имя):
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo(имя)
        return теперь.astimezone(z).utcoffset().total_seconds() / 3600.0
    except Exception:                                           # noqa: BLE001
        return 3.0

print("окно: %s-%s, дни %s, по зоне получателя=%s"
      % (окно.get("start"), окно.get("end"), окно.get("days"),
         окно.get("by_recipient_tz")))
print("сейчас UTC %s (Москва %s)"
      % (теперь.strftime("%H:%M"),
         (теперь + timedelta(hours=3)).strftime("%H:%M")))
print("")
print("--- когда открыто окно у наших получателей ---")
итого = 0
for з, n in sorted(зоны.items(), key=lambda x: -x[1]):
    ч = сдвиг(з)
    нач = (9 - ч) % 24
    кон = (14 - ч) % 24
    print("   %-20s писем %5d | окно %02d:00-%02d:00 UTC = %02d:00-%02d:00 МСК"
          % (з, n, нач, кон, (нач + 3) % 24, (кон + 3) % 24))
    итого += n

# 2. ёмкость ящиков Meyer на сутки
лимит = ушло = свободно = 0
ящиков = 0
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    ящиков += 1
    try:
        г = snd.mailbox_readiness(mb.mailbox_id, now=теперь)
        л = int(getattr(г, "daily_limit", 0) or 0)
        s = int(getattr(г, "sent_today", 0) or 0)
    except Exception:                                           # noqa: BLE001
        л = s = 0
    лимит += л
    ушло += s
свободно = max(0, лимит - ушло)

print("")
print("=" * 74)
print("=== КОГДА УЙДЁТ ПАРТИЯ ===")
print("писем партии в работе (pending+approved): %d" % итого)
print("ящиков Meyer: %d; дневной лимит суммарно: %d; уже ушло сегодня: %d; "
      "осталось на сегодня: %d" % (ящиков, лимит, ушло, свободно))
if лимит:
    print("при полной выборке лимита партия уйдёт примерно за %.1f рабочих дней"
          % (итого / float(лимит)))
print("по факту последних 7 дней Meyer отправлял ~142 письма в сутки, "
      "то есть %.0f рабочих дней" % (итого / 142.0))
