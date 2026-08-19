# -*- coding: utf-8 -*-
"""Прогнать заслон ловушек по очереди — с новым классом «заглушка».

19.08 письмо ушло на test@mail.ru и отбилось: заслон такого класса не знал.
Класс добавлен; этим прогоном добираем то, что уже лежит в очереди.

Без аргумента — сухой прогон.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe                          # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.lovushki import ЗаслонЛовушек                        # noqa: E402
from sender.store import Store                                   # noqa: E402

ПРИМЕНИТЬ = "--применить" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
try:
    probe = AddrProbe(cfg.get("service.db_path", r"C:\sender\sender.db"))
except Exception as ex:                                          # noqa: BLE001
    print("проба недоступна:", str(ex)[:90])
    probe = None

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, lower(COALESCE(email,'')), status FROM confirm_reviews "
        "WHERE campaign_id IN (10,11) AND status IN ('pending','approved')"
    ).fetchall()
письма = [{"id": r[0], "email": r[1], "status": r[2]} for r in ряды]
print(f"писем в очереди: {len(письма)}")

з = ЗаслонЛовушек(store=store, probe=probe)
нашли = з.найти(письма)
print(f"ловушек найдено: {len(нашли)}")
for н in нашли[:25]:
    print(f"  #{н.get('id')}  {н.get('email'):<34} {н.get('вид')}: "
          f"{str(н.get('почему'))[:70]}")
if not ПРИМЕНИТЬ:
    print("\nсухой прогон. Снять — аргумент --применить")
    raise SystemExit(0)
итог = з.применить(письма)
print("\nприменено:", итог)
