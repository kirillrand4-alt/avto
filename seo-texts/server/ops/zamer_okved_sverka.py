# -*- coding: utf-8 -*-
"""Сверка п.4: ObzvonIndex.equip_for_okved (карта в памяти) против прежнего
LIKE-запроса на тех же кодах. Только чтение (индекс обзвона открыт ro)."""
import random
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.company_card import ObzvonIndex  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
путь = str(cfg.get("obzvon.index_path", "") or "")
об = ObzvonIndex(путь)
assert hasattr(об, "_karta_okved"), "правка п.4 не стоит"
сырой = sqlite3.connect(f"file:{путь}?mode=ro", uri=True)
print("строк в obzvon:", сырой.execute("SELECT COUNT(*) FROM obzvon").fetchone()[0])
print("план старого запроса:", " | ".join(r[3] for r in сырой.execute(
    "EXPLAIN QUERY PLAN SELECT equip_by_okved FROM obzvon WHERE okved_main LIKE ? "
    "AND COALESCE(equip_by_okved,'')<>'' LIMIT 1", ("25%",))))


def старый(okved):
    код = str(okved or "").strip().split()[0] if str(okved or "").strip() else ""
    while код:
        row = сырой.execute(
            "SELECT equip_by_okved FROM obzvon WHERE okved_main LIKE ? AND "
            "COALESCE(equip_by_okved,'')<>'' LIMIT 1", (код + "%",)).fetchone()
        т = (row[0] or "").strip() if row else ""
        if т and т.lower() not in ("не найдено", "нет", "-", "—"):
            return т
        if "." not in код:
            break
        код = код.rsplit(".", 1)[0]
    return ""


t0 = time.perf_counter()
карта = об._karta_okved()
print(f"карта построена за {(time.perf_counter()-t0)*1000:.0f} мс, ключей {len(карта)}")

# коды из очереди: основной и дополнительные ОКВЭД писем pending
коды = set()
с = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
import json  # noqa: E402
for (pj,) in с.execute("SELECT panel_json FROM confirm_reviews WHERE status='pending'"):
    try:
        п = json.loads(pj or "{}")
    except Exception:  # noqa: BLE001
        continue
    к = str(((п.get("company") or {}).get("okved")) or "").strip()
    if к:
        коды.add(к.split()[0])
    for x in str((((п.get("company_full") or {}).get("reg") or {})
                  .get("okved_all_codes")) or "").split("|"):
        if x.strip():
            коды.add(x.strip())
все_осн = [r[0] for r in сырой.execute("SELECT DISTINCT okved_main FROM obzvon") if r[0]]
random.seed(7)
коды |= set(random.sample(все_осн, min(120, len(все_осн))))
коды |= {"99.99.9", "01", "25", "28.25", "71.12", "62.01", "46.69.9"}
print("кодов к сверке:", len(коды))
расх, t_old, t_new = 0, 0.0, 0.0
for к in sorted(коды):
    t0 = time.perf_counter(); а = старый(к); t_old += time.perf_counter() - t0
    t0 = time.perf_counter(); б = об.equip_for_okved(к); t_new += time.perf_counter() - t0
    if а != б:
        расх += 1
        if расх <= 10:
            print(f"  РАСХОЖДЕНИЕ {к!r}: старый={а[:60]!r} новый={б[:60]!r}")
print(f"расхождений: {расх} из {len(коды)}; старый путь {t_old:.1f} с всего "
      f"({t_old/len(коды)*1000:.0f} мс/код), новый {t_new*1000:.1f} мс всего")
print("=== ГОТОВО ===")
