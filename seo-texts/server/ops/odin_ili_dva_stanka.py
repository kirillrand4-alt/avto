# -*- coding: utf-8 -*-
"""Сколько мейеровских писем называют один станок, а сколько оба.

Владелец 19.08: «по мейеру готовая еда и кондитерка если, то там и рентген
и фотики скорее всего надо писать». Правило про два станка есть, но второй
разрешён как исключение - «если профиль даёт ЯВНУЮ задачу». Меряем, во
скольких письмах пищевого профиля назван только один.
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕНТГЕН = re.compile(r'(?i)рентген|инспекци\w*\s+упаков|металлодетект')
ФОТО = re.compile(r'(?i)фотосепарат|оптическ\w*\s+сортиров|сортировк\w*\s+'
                  r'(сырь|зерн|ореx|орех|крупы)')
# Пищевые профили, где по слову владельца нужны ОБА станка
# СЫПУЧЕЕ СЫРЬЁ, А НЕ «ЛЮБАЯ ЕДА». Первая редакция считала пищевым
# профилем и мясные полуфабрикаты, и рыбу - и записала в промахи шесть
# писем, где один рентген был правильным ответом: филе лосося и фарш
# фотосепаратором не сортируют. Ловим только то, где поток сыпучий.
ПИЩЕВОЙ = re.compile(
    r'(?i)кондитер|выпечк|хлебобулочн|мука|муком|крупа|крупян|зерн|'
    r'орех|сухофрукт|мюсли|батончик|шоколад|конфет|пряник|печенье|'
    r'снек|семечк|бобов|специ|чай\b|кофе|какао|сухие\s+смеси|'
    r'сыпуч|комбикорм|солод')

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(c.edited_body, c.body, ''),
                  COALESCE(rc.company_name,''), COALESCE(m.status,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN messages m ON m.id=c.message_id
            WHERE c.campaign_id IN (7,8,9,11)""").fetchall()

счёт = Counter()
одиночки = []
for rid, st, тело, фирма, mst in ряды:
    т = str(тело or "")
    if not т.strip():
        continue
    пищевое = bool(ПИЩЕВОЙ.search(т))
    р, ф = bool(РЕНТГЕН.search(т)), bool(ФОТО.search(т))
    вид = ("оба станка" if р and ф else
           "только рентген" if р else
           "только фотосепаратор" if ф else "станок не назван")
    счёт[f"{'пищевое' if пищевое else 'прочее'}: {вид}"] += 1
    if пищевое and вид in ("только рентген", "только фотосепаратор"):
        счёт[f"  из них {st}"] += 1
        if st == "pending":
            одиночки.append((rid, фирма, вид))

print(f"мейеровских писем: {len(ряды)}")
for k, n in sorted(счёт.items()):
    print(f"  {n:>4}  {k}")
print(f"\nпищевые письма с одним станком, ждут решения: {len(одиночки)}")
for rid, фирма, вид in одиночки[:15]:
    print(f"  #{rid:<6} {str(фирма)[:40]:<42} {вид}")
