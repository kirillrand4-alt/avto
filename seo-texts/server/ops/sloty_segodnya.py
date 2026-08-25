# -*- coding: utf-8 -*-
"""У всех ли писем очереди законный слот отправки.

Дисциплину часа при by_recipient_tz несёт именно scheduled_at: воротник
_within_window час получателя не проверяет. Значит письмо со слотом «сейчас»
уедет во владивостокские 16:00, если его поставили в московские 09:00.
Проверяем каждое письмо очереди в ЗОНЕ ЕГО ПОЛУЧАТЕЛЯ.
"""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, time as dtime, timezone

sys.path.insert(0, r"C:\sender\sender")
try:
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001
    ZoneInfo = None

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
окно = json.loads(c.execute(
    "SELECT value FROM panel_settings WHERE key='sending_window'").fetchone()[0])
print("окно: %s" % окно)
ДНИ = {int(д) for д in (окно.get("days") or [])} or {1, 2, 3, 4, 5}
НАЧ = dtime(*[int(x) for x in str(окно.get("start", "09:00")).split(":")[:2]])
КОН = dtime(*[int(x) for x in str(окно.get("end", "18:00")).split(":")[:2]])
ПОЗОНЕ = bool(окно.get("by_recipient_tz"))
ОБЩАЯ = str(окно.get("tz") or "Europe/Moscow")


def зона(имя):
    try:
        return ZoneInfo(имя)
    except Exception:  # noqa: BLE001
        return timezone.utc


сейчас = datetime.now(timezone.utc)
кол = [р[1] for р in c.execute("PRAGMA table_info(recipients)")]
поле_tz = "tz" if "tz" in кол else None
print("зона получателя в recipients: %s" % (поле_tz or "НЕТ ПОЛЯ"))

ряды = c.execute(
    "SELECT m.id, m.scheduled_at, m.updated_at, r.email%s "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status IN ('scheduled','sending')"
    % (", r.%s tz" % поле_tz if поле_tz else ", NULL tz")).fetchall()
print("в очереди: %d" % len(ряды))

итог, часы, зоны = Counter(), Counter(), Counter()
плохие = []
for р in ряды:
    s = р["scheduled_at"]
    if not s:
        итог["слота нет вовсе"] += 1
        плохие.append((р["id"], р["email"], "нет слота"))
        continue
    try:
        т = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if not т.tzinfo:
            т = т.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        итог["слот не разобрался"] += 1
        continue
    имя_з = str(р["tz"]) if (ПОЗОНЕ and р["tz"]) else ОБЩАЯ
    зоны[имя_з] += 1
    мест = т.astimezone(зона(имя_з))
    часы["%s %02d:00" % (мест.strftime("%d.%m"), мест.hour)] += 1
    в_окне = мест.isoweekday() in ДНИ and НАЧ <= мест.time() <= КОН
    прошло = т <= сейчас
    if not в_окне:
        итог["слот ВНЕ окна получателя"] += 1
        if len(плохие) < 400:
            плохие.append((р["id"], р["email"],
                           "%s %s" % (мест.strftime("%d.%m %H:%M"), имя_з)))
    elif прошло:
        итог["в окне, срок настал (уйдёт сегодня)"] += 1
    else:
        итог["в окне, ждёт своего часа"] += 1

print("\n=== СЛОТЫ ===")
for к, н in итог.most_common():
    print("   %-42s %5d" % (к, н))
print("\n=== ПО ЧАСАМ (местное время получателя) ===")
for к, н in sorted(часы.items())[:14]:
    print("   %-14s %5d" % (к, н))
print("\n=== ЗОНЫ ПОЛУЧАТЕЛЕЙ ===")
for к, н in зоны.most_common(8):
    print("   %-22s %5d" % (к, н))
if плохие:
    print("\nпримеры писем вне окна:")
    for и, п, ч in плохие[:8]:
        print("   #%-7s %-34s %s" % (и, str(п)[:34], ч))
