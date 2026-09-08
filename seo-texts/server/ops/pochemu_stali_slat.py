# -*- coding: utf-8 -*-
"""Почему письма перестали уходить: срок, окно, гейты, лимиты, ящик."""
import sys, time
from collections import Counter
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
from sender.auto_send import window_from                        # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
gates = Gates(cfg, store)
snd = Sender(cfg, store, Suppression(store), gates, dry_run=True)
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)


def сдвиг(имя):
    try:
        from zoneinfo import ZoneInfo
        return теперь.astimezone(ZoneInfo(имя)).utcoffset().total_seconds() / 3600.0
    except Exception:                                           # noqa: BLE001
        return 3.0


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# 1. отправки по получасам за последние 4 часа
корзины = Counter()
with store._lock:
    for р in store._conn.execute(
            "SELECT sent_at FROM messages WHERE status='sent' "
            "  AND sent_at >= datetime('now','-4 hours')"):
        т = str(р["sent_at"] or "").replace("T", " ")
        корзины[т[:15] + "0"] += 1
print("--- отправлено по 10 минут (UTC) ---")
for к in sorted(корзины)[-14:]:
    print("   %s  %4d" % (к, корзины[к]))
if not корзины:
    print("   за 4 часа ни одного письма")

# 2. что стоит и созрело ли
готовы = Counter()
with store._lock:
    строки = store._conn.execute(
        """SELECT m.id, m.scheduled_at, m.mailbox_id, r.tz, r.email
             FROM messages m LEFT JOIN recipients r ON m.recipient_id = r.id
            WHERE m.status='scheduled'""").fetchall()
for р in строки:
    d = разбор(р["scheduled_at"])
    срок = (d is not None and d <= теперь)
    ч = сдвиг(str(р["tz"] or "Europe/Moscow"))
    мест = (теперь + timedelta(hours=ч))
    в_окне = (9 <= мест.hour < 14) and (мест.isoweekday() in (окно.get("days") or [1,2,3,4,5]))
    готовы["срок %s / окно %s" % ("есть" if срок else "нет",
                                  "открыто" if в_окне else "закрыто")] += 1
print("")
print("--- %d писем в статусе scheduled ---" % len(строки))
for к, в in готовы.most_common():
    print("   %-34s %5d" % (к, в))

# 3. гейты и ящики
г = gates.check_global()
print("")
print("--- гейты ---")
print("   глобальный: tripped=%s %s"
      % (getattr(г, "tripped", "?"), str(getattr(г, "reason", ""))[:80]))
блок = Counter()
свободно = 0
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    гм = gates.check_mailbox(mb.mailbox_id)
    st = store.get_mailbox_state(mb.mailbox_id)
    гот = snd.mailbox_readiness(mb.mailbox_id, now=теперь)
    л = int(getattr(гот, "daily_limit", 0) or 0)
    s = int(getattr(гот, "sent_today", 0) or 0)
    свободно += max(0, л - s)
    if getattr(гм, "tripped", False):
        блок["гейт ящика: " + str(getattr(гм, "reason", ""))[:40]] += 1
    elif st is not None and getattr(st, "paused", False):
        блок["на паузе"] += 1
    elif l_exhausted := (л and s >= л):
        блок["лимит дня выбран"] += 1
    elif not snd.can_send_now(mb.mailbox_id, now=теперь, manual=False):
        блок["can_send_now=False (окно/пейсинг)"] += 1
    else:
        блок["ГОТОВ СЛАТЬ"] += 1
print("")
print("=" * 74)
print("=== ПОЧЕМУ НЕ УХОДЯТ ===")
print("сейчас UTC %s (Москва %s)"
      % (теперь.strftime("%H:%M"), (теперь + timedelta(hours=3)).strftime("%H:%M")))
for к, в in блок.most_common():
    print("   ящиков Meyer: %-40s %3d" % (к, в))
print("   свободного дневного лимита суммарно: %d" % свободно)
