# -*- coding: utf-8 -*-
"""Проставить получателям партии настоящую часовую зону вместо московской.

В загрузчике стояло tz="Europe/Moscow" для всех - моя ошибка. Окно отправки
считается по зоне получателя (by_recipient_tz), поэтому хозяйство в
Алтайском крае получало бы письмо в 09:00 МСК, то есть в 13:00 по себе:
окно 09:00-14:00 у него почти закончилось. Зона берётся из кода региона в
ИНН - тем же способом, каким уже заполнено поле region.

    python pochinit_zony_agro.py            # вхолостую
    python pochinit_zony_agro.py --primenit
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ИСТОЧНИКИ = ("чеко-агро-2026", "чеко-агро-2026-второй")
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

# Код региона в ИНН -> зона IANA. Коды те же, что в РЕГИОНАХ загрузчика.
ЗОНЫ = {}


def _пометить(зона, коды):
    for к in коды.split():
        ЗОНЫ[к.strip()] = зона


_пометить("Europe/Kaliningrad", "39")
_пометить("Europe/Moscow",
          "01 05 06 07 08 09 10 11 12 13 15 16 20 21 23 26 29 31 32 33 34 35 "
          "36 37 40 44 46 47 48 50 51 52 53 57 58 60 61 62 67 68 69 71 76 77 "
          "78 83 91 92 93 94 95 99 "
          # Вторые коды регионов, которых не было в РЕГИОНАХ загрузчика:
          # 90 Московская область, 43 Кировская, 97 Москва.
          "90 43 97")
_пометить("Europe/Samara", "63 73 18")
_пометить("Europe/Astrakhan", "30")
_пометить("Europe/Saratov", "64")
_пометить("Asia/Yekaterinburg", "02 45 56 59 66 72 74 86 89")
_пометить("Asia/Omsk", "55")
_пометить("Asia/Barnaul", "04 22")
_пометить("Asia/Krasnoyarsk", "17 19 24")
_пометить("Asia/Novokuznetsk", "42")
_пометить("Asia/Novosibirsk", "54")
_пометить("Asia/Tomsk", "70")
_пометить("Asia/Irkutsk", "03 38 85")   # 85 - бывший Усть-Ордынский АО
_пометить("Asia/Yakutsk", "14 28")
_пометить("Asia/Chita", "75")
_пометить("Asia/Vladivostok", "25 27 79")
_пометить("Asia/Magadan", "49")
_пометить("Asia/Sakhalin", "65")
_пометить("Asia/Kamchatka", "41")
_пометить("Asia/Anadyr", "87")

store = Store(r"C:\sender\sender.db")
счёт = Counter()
нераспознанные = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        "SELECT id, inn, tz, region FROM recipients WHERE source IN (?,?)",
        ИСТОЧНИКИ).fetchall()
for р in строки:
    инн = "".join(c for c in str(р["inn"] or "") if c.isdigit())
    зона = ЗОНЫ.get(инн[:2]) if len(инн) >= 2 else None
    if not зона:
        счёт["код региона не распознан — оставляем как есть"] += 1
        нераспознанные[инн[:2] or "??"] += 1
        continue
    если = str(р["tz"] or "")
    if если == зона:
        счёт["уже верная: " + зона] += 1
        continue
    правки.append((int(р["id"]), зона))
    счёт["К ПРАВКЕ: " + зона] += 1

if ПРИМЕНИТЬ and правки:
    сделано = 0
    for нач in range(0, len(правки), 500):
        кусок = правки[нач:нач + 500]
        with store.transaction() as conn:
            for rid, зона in кусок:
                conn.execute("UPDATE recipients SET tz=?, updated_at="
                             "datetime('now') WHERE id=?", (зона, rid))
        сделано += len(кусок)
    счёт["ПЕРЕПИСАНО"] = сделано

print("=" * 74)
print("=== ЧАСОВЫЕ ЗОНЫ ПАРТИИ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common(30):
    print("   %-46s %5d" % (к, в))
if нераспознанные:
    print("")
    print("нераспознанные коды региона: %s"
          % ", ".join("%s:%d" % (к, в) for к, в in нераспознанные.most_common(15)))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Проставить — --primenit")
