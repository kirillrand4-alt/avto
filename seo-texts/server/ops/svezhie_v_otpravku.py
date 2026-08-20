# -*- coding: utf-8 -*-
"""Свежие письма из очереди — в отправку, с проверкой каждого адреса.

Прогон генерации кладёт письмо в очередь подтверждения как pending: оно
написано и прошло гейты текста, но слота отправки у него нет. Владелец
19.08: «перекинь в отправку годные письма» и «у всех почт убедись что
прошли все проверки из тех что отправятся».

Проверки те же, что у сводки на завтра, каждая своим заслоном:
  * формат адреса;
  * приговор пробы («нет ящика» / «нет MX») — письмо физически не дойдёт;
  * заслон подтверждения (стоп-лист, свежий контакт <90 дней, недоставимый);
  * адрес-заглушка (info@ и прочие ловушки).

Без --katit только показывает.
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

ПОРОГ = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))
КАТИТЬ = "--katit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
АДР = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")

with store._lock:
    строки = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.recipient_id, c.message_id, c.email, "
        "       r.inn, COALESCE(p.verdict,'') proba "
        "FROM confirm_reviews c "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "LEFT JOIN addr_probe p ON p.email=lower(c.email) "
        "WHERE c.id >= ? AND c.status='pending'", (ПОРОГ,)).fetchall()

счёт = Counter()
годные = []
for r in строки:
    e = str(r["email"] or "").strip().lower()
    плохо = []
    if not АДР.match(e):
        плохо.append("формат адреса")
    if str(r["proba"]) in ("нет ящика", "нет MX"):
        плохо.append(f"приговор пробы: {r['proba']}")
    try:
        причина = cs._guard(inn=str(r["inn"] or ""), email=e)
        if причина:
            плохо.append(f"заслон: {причина.split(':')[0]}")
    except Exception as ex:                                      # noqa: BLE001
        плохо.append(f"заслон не отработал: {str(ex)[:40]}")
    try:
        from sender.lovushki import заглушка
        if заглушка(e):
            плохо.append("адрес-заглушка")
    except Exception:                                            # noqa: BLE001
        pass
    if плохо:
        for p in плохо:
            счёт[p] += 1
    else:
        годные.append(r)
        счёт["чисто — в отправку"] += 1

print(f"карточек pending с id >= {ПОРОГ}: {len(строки)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

одобрено = слотов = 0
слоты = Counter()
for r in годные:
    try:
        ок = store.confirm_decide(int(r["id"]), status="approved",
                                  decided_by="партия 20.08")
        if ок is False:
            continue
        одобрено += 1
        rec = store.get_recipient(r["recipient_id"])
        if r["message_id"] and rec is not None:
            с = next_slot(окно, recipient_tz_name(окно, rec), сейчас)
            store.reschedule_message(int(r["message_id"]), с)
            слотов += 1
            слоты[str(с)[:10]] += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не одобрилось: {str(ex)[:90]}")

print(f"\nодобрено в отправку: {одобрено} (слотов поставлено {слотов})")
print("слоты по дням:", dict(слоты))
