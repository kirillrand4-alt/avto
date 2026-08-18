# -*- coding: utf-8 -*-
"""Работает ли отправка ПО ВРЕМЕНИ ПОЛУЧАТЕЛЯ - замером, а не по коду.

Владелец: «проверь что работает именно отправка по времени получателя».
Вопрос не праздный: 48 писем уже в автоотправке.

Цепочка в коде такая, и рвётся она в трёх местах:
  1. НАСТРОЙКА. sender._within_window читает panel_settings/sending_window.
     Если там нет by_recipient_tz, воротник режет час по ОДНОЙ зоне, и
     «утро получателя» превращается в утро Москвы.
  2. ЗОНА ПОЛУЧАТЕЛЯ. cadence._shift_into_window(tz_name=recipient.tz)
     ставит письмо на 09:00-11:00 в зоне ПОЛУЧАТЕЛЯ. Если колонка
     recipients.tz пуста, зоны нет и всё уезжает в зону окна.
  3. ЧАС ПИСЬМА. У писем должно стоять РАЗНОЕ время по UTC - у Владивостока
     раньше, у Калининграда позже. Если у всех один час, значит по зонам
     никто не раскладывал.

Меряем все три.

    python zapusk_svoego_skripta.py ops/proverka_vremeni_poluchatelya.py
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- 1. настройка окна ----------------------------------------------------- #
print("1) НАСТРОЙКА ОКНА")
ov = None
try:
    ov = store.get_setting("sending_window")
except Exception as ex:                                         # noqa: BLE001
    print(f"   panel_settings не прочитались: {str(ex)[:120]}")
print(f"   panel_settings/sending_window = {ov!r}")
try:
    w = cfg.sending_window()
    print(f"   sender.yaml окно: дни {list(w.days)} {w.start}-{w.end} "
          f"зона {w.tz}")
except Exception as ex:                                         # noqa: BLE001
    print(f"   окно из yaml не прочиталось: {str(ex)[:120]}")
по_получателю = bool(isinstance(ov, dict) and ov.get("by_recipient_tz"))
print(f"   ПО ВРЕМЕНИ ПОЛУЧАТЕЛЯ: "
      f"{'ВКЛЮЧЕНО' if по_получателю else 'ВЫКЛЮЧЕНО'}")
if not по_получателю:
    print("   -> час письма будет резаться по ОДНОЙ зоне; утро Владивостока "
          "для такого воротника - ночь")

# --- 2. зона у получателей ------------------------------------------------- #
print("\n2) ЗОНА У ПОЛУЧАТЕЛЕЙ (колонка recipients.tz)")
with store._lock:
    строки = store._conn.execute(
        "SELECT r.id, COALESCE(r.tz,''), COALESCE(r.region,''), c.id, c.status "
        "FROM confirm_reviews c JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.campaign_id=10 AND c.status IN ('approved','pending')"
    ).fetchall()
зоны = Counter()
одобренные = []
for rid, tz, region, cid, статус in строки:
    зоны[(tz or "(пусто)")] += 1
    if статус == "approved":
        одобренные.append((cid, tz, region))
всего = max(1, len(строки))
пусто = зоны.get("(пусто)", 0)
print(f"   писем кампании 10 (approved+pending): {len(строки)}")
print(f"   зона НЕ заполнена у {пусто} ({100.0 * пусто / всего:.0f}%)")
for z, n in зоны.most_common(12):
    print(f"     {z:<24} {n}")

print(f"\n   из них ОДОБРЕННЫХ (уже в автоотправке): {len(одобренные)}")
зоны_одобр = Counter(tz or "(пусто)" for _c, tz, _r in одобренные)
for z, n in зоны_одобр.most_common(12):
    print(f"     {z:<24} {n}")

# --- 3. на какой час реально поставлены письма ----------------------------- #
print("\n3) НА КАКОЙ ЧАС ПОСТАВЛЕНЫ ПИСЬМА")
with store._lock:
    имена = [d[1] for d in store._conn.execute(
        "PRAGMA table_info(messages)")]
    поле = next((p for p in ("scheduled_at", "send_after", "next_attempt_at",
                             "planned_at") if p in имена), None)
print(f"   поле расписания в messages: {поле or 'НЕ НАЙДЕНО'}")
if поле:
    with store._lock:
        ряд = store._conn.execute(
            f"SELECT COALESCE(r.tz,''), m.{поле} FROM messages m "
            "JOIN recipients r ON r.id=m.recipient_id "
            f"WHERE m.{поле} IS NOT NULL AND m.{поле} <> '' "
            "ORDER BY m.id DESC LIMIT 400").fetchall()
    часы = {}
    for tz, когда in ряд:
        try:
            t = datetime.fromisoformat(str(когда).replace("Z", "+00:00"))
        except Exception:                                       # noqa: BLE001
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        часы.setdefault(tz or "(пусто)", Counter())[t.astimezone(
            timezone.utc).hour] += 1
    if not часы:
        print("   расписаний нет - письма ещё не планировались")
    for tz, c in sorted(часы.items()):
        топ = ", ".join(f"{ч}:00 UTC x{n}" for ч, n in c.most_common(4))
        print(f"   {tz:<24} {топ}")
    print("\n   Если у разных зон РАЗНЫЙ час UTC - раскладка по зонам живая.")
    print("   Если у всех один и тот же час - по зонам никто не раскладывал.")
