# -*- coding: utf-8 -*-
"""Когда уйдут ждущие мейеровские письма и кто передвинул им срок.

Первый прогон показал главное: из 62 одобренных НИ ОДНО не созрело —
scheduled_at у всех в будущем. Здесь выясняем, кто и на какое время их
подвинул: часовой пояс получателя, что даёт next_slot прямо сейчас, и
совпадает ли поставленный срок с расчётным.
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (window_from, within_window_now,          # noqa: E402
                              recipient_tz_name, next_slot)
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 11
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
now = datetime.now(timezone.utc)
win = window_from(store, cfg)
МСК = ZoneInfo("Europe/Moscow")

print(f"== кампания {КАМПАНИЯ} | сейчас {now.strftime('%H:%M')} UTC "
      f"= {now.astimezone(МСК).strftime('%H:%M')} МСК ==")
print("  окно:", win)

with store._lock:
    строки = store._conn.execute(
        "SELECT m.id, m.recipient_id, m.scheduled_at, m.updated_at, "
        "       r.email, r.tz "
        "FROM messages m JOIN confirm_reviews c ON c.message_id=m.id "
        "LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE c.campaign_id=? AND m.status='scheduled' "
        "AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id "
        "     ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited') "
        "ORDER BY m.scheduled_at, m.id", (КАМПАНИЯ,)).fetchall()

print(f"  одобрено и ждёт: {len(строки)}")

по_зоне = Counter()
по_сроку = defaultdict(list)
расчёт_совпал = Counter()
сегодня_можно = []
for r in строки:
    rec = store.get_recipient(r["recipient_id"])
    tzn = recipient_tz_name(win, rec)
    по_зоне[f"{r['tz'] or '—'} -> считаем в {tzn}"] += 1
    сейчас_открыто = within_window_now(win, tzn, now)
    слот = next_slot(win, tzn, now)
    по_сроку[str(r["scheduled_at"])[:16]].append(r["id"])
    поставлено = str(r["scheduled_at"])[:16]
    расчёт = слот.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    расчёт_совпал["совпадает" if поставлено == расчёт
                  else f"НЕ совпадает (расчёт {расчёт})"] += 1
    if сейчас_открыто:
        сегодня_можно.append((r["id"], tzn, поставлено, r["email"]))

print("\n== часовые пояса ждущих ==")
for k, v in по_зоне.most_common():
    print(f"  {v:>4}  {k}")

print("\n== на какое время передвинуты (UTC / МСК) ==")
for срок in sorted(по_сроку):
    ids = по_сроку[срок]
    try:
        мск = datetime.strptime(срок, "%Y-%m-%dT%H:%M").replace(
            tzinfo=timezone.utc).astimezone(МСК).strftime("%d.%m %H:%M")
    except Exception:                                                  # noqa: BLE001
        мск = "?"
    print(f"  {срок} UTC (= {мск} МСК): {len(ids):>3} шт  "
          f"пример #{ids[0]}")

print("\n== окно получателя открыто ПРЯМО СЕЙЧАС ==")
print(f"  таких писем: {len(сегодня_можно)}")
for i, t in enumerate(сегодня_можно[:12]):
    print(f"    #{t[0]:<6} tz={t[1]:<20} срок={t[2]}  {t[3]}")

print("\n== сходится ли поставленный срок с расчётом next_slot ==")
for k, v in расчёт_совпал.most_common():
    print(f"  {v:>4}  {k}")

print("\n== когда письма правились (updated_at) ==")
пр = Counter(str(r["updated_at"])[:13] for r in строки)
for k in sorted(пр):
    print(f"  {k}:00 UTC  -> {пр[k]} писем")
