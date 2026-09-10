# -*- coding: utf-8 -*-
"""Пустить вперёд адреса, про которые проба сказала «есть».

Владелец 10.09: «сначала спаси репутацию, перемести почты которые точно
есть в начало».

Почему это работает. Провайдер судит отправителя по доле отбивок. Адрес с
вердиктом «есть» отбиться почти не может - его существование подтвердил сам
почтовый сервер. Адрес на катч-олл-домене («принимает всё») проверить
нельзя в принципе: сервер отвечает «да» на любое имя, и есть ящик или нет,
выяснится только отбивкой. Пуская подтверждённые вперёд, мы набираем
хорошую историю доставки раньше, чем рискуем.

Порядок срока отправки:
  «есть»                       - ближайшее окно;
  катч-олл, «неясно», без пробы - на три часа позже;
  «отказ пробе»                - в самый хвост, ещё на три часа;
  «нет ящика» / «нет MX»       - снимаем с очереди совсем.

Срок только СДВИГАЕТСЯ ВНУТРИ окна: next_slot сам приводит время к
разрешённым дням и часам зоны получателя.

    python poryadok_po_verdiktu.py            # вхолостую
    python poryadok_po_verdiktu.py --primenit
"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.auto_send import next_slot, window_from             # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СДВИГ_КЭТЧОЛЛ = timedelta(hours=3)
СДВИГ_ОТКАЗ = timedelta(hours=6)
МЁРТВЫЕ = ("нет ящика", "нет MX")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)

with store._lock:
    пробы = {str(r["email"] or "").lower(): str(r["verdict"] or "")
             for r in store._conn.execute("SELECT email, verdict FROM addr_probe")}
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.email, c.status AS cst,
                  m.id AS mid, m.status AS mst, m.scheduled_at, r.tz
             FROM confirm_reviews c
             JOIN messages m ON c.message_id = m.id
             LEFT JOIN recipients r ON c.recipient_id = r.id
            WHERE c.subject IN (%s) AND m.status='scheduled'"""
        % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)).fetchall()

счёт = Counter()
сдвиги = []
снять = []
for р in строки:
    а = str(р["email"] or "").lower()
    в = пробы.get(а) or "без вердикта"
    зона = str(р["tz"] or "Europe/Moscow")
    if в in МЁРТВЫЕ:
        снять.append((int(р["cid"]), int(р["mid"]), а, в))
        счёт["СНЯТЬ (%s)" % в] += 1
        continue
    if в == "есть":
        когда = next_slot(окно, зона, теперь)
        счёт["вперёд: есть"] += 1
    elif в == "отказ пробе":
        когда = next_slot(окно, зона, теперь + СДВИГ_ОТКАЗ)
        счёт["в хвост: отказ пробе"] += 1
    else:
        когда = next_slot(окно, зона, теперь + СДВИГ_КЭТЧОЛЛ)
        счёт["позже: %s" % в] += 1
    сдвиги.append((int(р["mid"]), когда))

if ПРИМЕНИТЬ:
    from sender.confirm import ConfirmSend                      # noqa: E402
    from sender.suppression import Suppression                  # noqa: E402
    cs = ConfirmSend(cfg, store, Suppression(store))
    сдвинуто = 0
    for нач in range(0, len(сдвиги), 400):
        with store.transaction() as conn:
            for mid, когда in сдвиги[нач:нач + 400]:
                conn.execute(
                    "UPDATE messages SET scheduled_at=?, updated_at="
                    "datetime('now') WHERE id=? AND status='scheduled'",
                    (когда.strftime("%Y-%m-%dT%H:%M:%S.%f"), mid))
                сдвинуто += 1
    счёт["СРОК ПЕРЕСТАВЛЕН"] = сдвинуто
    убрано = 0
    for cid, mid, а, в in снять:
        try:
            if cs._store.confirm_decide(
                    cid, status="skipped",
                    decided_by="порядок по вердикту пробы",
                    reason="приговор пробы: %s" % в):
                убрано += 1
        except Exception as ex:                                 # noqa: BLE001
            print("   карточка %s не снялась: %s" % (cid, str(ex)[:80]))
        try:
            store.mark_skipped_if_not_terminal(
                mid, "порядок по вердикту пробы: %s" % в)
        except Exception:                                       # noqa: BLE001
            pass
    счёт["СНЯТО С ОЧЕРЕДИ"] = убрано

for cid, mid, а, в in снять[:10]:
    print("   снимаем: %-38s %s" % (а[:38], в))
print("")
print("=" * 74)
print("=== ПОРЯДОК ПО ВЕРДИКТУ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("писем со сроком отправки: %d" % len(строки))
for к, в in счёт.most_common(12):
    print("   %-40s %5d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Переставить — --primenit")
