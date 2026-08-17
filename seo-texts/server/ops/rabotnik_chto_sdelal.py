# -*- coding: utf-8 -*-
"""Что работник на VPS реально сделал: считаем по его собственному файлу.

Живость работника меряется ТОЛЬКО свежестью строк в probe-rezultat.jsonl на
дропе - не приростом addr_probe (туда пишет и проба с сервера) и не пульсом
(пульс идёт и у бездельника). Забираем файл штатным путём, применяем
вердикты и считаем, сколько строк датировано сегодня.
"""
import json
import sys
import time
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                 # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.probe_sync import build_probe_sync                 # noqa: E402
from sender.store import Store                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
loop = build_addr_probe(store, cfg)
sync = build_probe_sync(store, loop.probe_, cfg)

сегодня = date.today().isoformat()
сырое = sync._дроп("GET", "probe-rezultat.jsonl").decode("utf-8", "replace")
строки = []
for s in сырое.splitlines():
    if not s.strip():
        continue
    try:
        строки.append(json.loads(s))
    except Exception:                                          # noqa: BLE001
        pass

свежие = [z for z in строки if str(z.get("ts") or "").startswith(сегодня)]
print(f"строк в файле работника: {len(строки)} | СЕГОДНЯШНИХ: {len(свежие)}")
if свежие:
    print("вердикты сегодняшних:",
          dict(Counter(str(z.get("verdict")) for z in свежие)))
    print("первая сегодняшняя:", str(свежие[0].get("ts"))[:19],
          "| последняя:", str(свежие[-1].get("ts"))[:19])
    print("\nпримеры:")
    for z in свежие[-5:]:
        print(f"  {str(z.get('email'))[:40]:<42} {str(z.get('verdict')):<14} "
              f"{str(z.get('answer'))[:50]}")

итог = sync.забрать()
print("\nприменено в панель:", итог)
print("сейчас:", time.strftime("%H:%M:%S"))
