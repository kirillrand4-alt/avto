# -*- coding: utf-8 -*-
"""Пересчитать срок отправки тем письмам, кому его считали по неверной зоне.

scheduled_at считается ОДИН РАЗ, при подтверждении, функцией next_slot по
зоне получателя. Письма, одобренные до вчерашней правки зон, получили срок
по московскому времени, хотя хозяйство стоит в Барнауле или Екатеринбурге:
у них окно уже открыто, а письмо ждёт 09:00 МСК.

Пересчитываем тем же next_slot, что и панель. Срок только приближаем, не
отодвигаем: письмо, которому и так пора, не трогаем.

    python podtyanut_pod_okno_agro.py            # вхолостую
    python podtyanut_pod_okno_agro.py --primenit
"""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.auto_send import next_slot, window_from             # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


счёт = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        """SELECT m.id, m.scheduled_at, r.tz, r.email
             FROM messages m
             JOIN confirm_reviews c ON c.message_id = m.id
             LEFT JOIN recipients r ON m.recipient_id = r.id
            WHERE m.status='scheduled' AND c.subject=?""", (ТЕМА,)).fetchall()
for р in строки:
    счёт["писем партии в scheduled"] += 1
    было = разбор(р["scheduled_at"])
    зона = str(р["tz"] or "Europe/Moscow")
    надо = next_slot(окно, зона, теперь)
    if было is None:
        счёт["срок не разобран"] += 1
        continue
    if надо >= было:
        счёт["срок и так не позже: " + зона] += 1
        continue
    правки.append((int(р["id"]), надо, зона, было))
    счёт["ПОДТЯНУТЬ: " + зона] += 1

if ПРИМЕНИТЬ and правки:
    with store.transaction() as conn:
        for mid, надо, _з, _б in правки:
            conn.execute("UPDATE messages SET scheduled_at=?, updated_at="
                         "datetime('now') WHERE id=? AND status='scheduled'",
                         (надо.strftime("%Y-%m-%dT%H:%M:%S.%f"), mid))
    счёт["ПОДТЯНУТО"] = len(правки)

for mid, надо, зона, было in правки[:10]:
    print("   письмо %-7s %-20s было %s → станет %s"
          % (mid, зона, было.strftime("%m-%d %H:%M"), надо.strftime("%m-%d %H:%M")))
print("")
print("=" * 74)
print("=== СРОК ОТПРАВКИ ПО ЗОНЕ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("сейчас UTC %s" % теперь.strftime("%m-%d %H:%M"))
for к, в in счёт.most_common(14):
    print("   %-44s %5d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Подтянуть — --primenit")
