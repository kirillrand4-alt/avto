# -*- coding: utf-8 -*-
"""Показать глазами: претензии рецензента к письмам, стоящим в очереди.

Владелец 20.08: «посмотри глазами что не прошло и если наш профиль но мало
данных - отправляй». Значит надо видеть саму претензию и знать, открылся
ли сайт: «нечем проверить» с пустым сайтом и «не годно» по существу —
разные случаи.
"""
import io
import json
import sqlite3
import sys

ЖУРНАЛ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ВЕРДИКТ = sys.argv[1] if len(sys.argv) > 1 else "не годно"
СКОЛЬКО = int(next((a for a in sys.argv[2:] if a.isdigit()), "60"))
# Хвост stdout у раннера короткий: показываем окно, а не всё сразу.
ПРОПУСТИТЬ = int(next((a.split("=",1)[1] for a in sys.argv[1:]
                       if a.startswith("--ot=")), "0"))

верд = {}
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        pass

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ФИЛЬТР = next((" AND campaign_id IN (%s)" % a.split("=",1)[1]
               for a in sys.argv[1:] if a.startswith("--kamp=")), "")
ряды = c.execute("SELECT id, campaign_id, email, subject FROM confirm_reviews "
                 "WHERE status='pending'" + ФИЛЬТР + " ORDER BY id").fetchall()
n = 0
for r in ряды:
    z = верд.get(r["id"])
    if not z or str(z.get("verdict") or "") != ВЕРДИКТ:
        continue
    n += 1
    if n <= ПРОПУСТИТЬ:
        continue
    if n > ПРОПУСТИТЬ + СКОЛЬКО:
        break
    пр = z.get("pretenzii") or []
    if isinstance(пр, str):
        пр = [пр]
    камп = "КЦ" if int(r["campaign_id"]) == 10 else "Meyer"
    print(f"#{r['id']} [{камп}] {str(z.get('фирма') or '')[:40]:<40} "
          f"сайт={z.get('сайт_знаков')} зн  {str(z.get('url') or '')[:40]}")
    for p in пр[:3]:
        print(f"      · {str(p)[:230]}")
print(f"\nпоказано {min(n, СКОЛЬКО)} из {n}")
