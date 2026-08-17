# -*- coding: utf-8 -*-
"""Почему в письмах партии почти нет имён: где теряется каждое.

Владелец: «про имя вроде обсудили, какие брать безопасно, но имён тоже не
вижу в письмах». Замер подтверждает: в кампании 10 именное приветствие у 4
писем из 468 (1%), в согласованных отправленных - 47 из 263 (18%).

Разница может быть трёх родов, и они лечатся по-разному:
  * имени НЕТ В КАРТОЧКЕ вовсе - тогда вопрос к обогащению, а не к письмам;
  * имя есть, но НЕ ПРОШЛО заслон (инициалы вместо полного, ящик его не
    подтверждает, роль ящика общая) - тогда вопрос к строгости правила;
  * имя прошло заслон, а модель им не воспользовалась - тогда вопрос к
    промпту.

Считаем воронку на письмах кампании поимённо, чтобы стало видно, какой из
трёх случаев главный.

    python zapusk_svoego_skripta.py ops/pochemu_net_imyon.py 10
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import (_imennoe_privetstvie,             # noqa: E402
                              _imya_soglasuetsya_s_yashchikom,
                              _polnoe_imya)
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ОБЩИЕ_РОЛИ = ("приёмная", "общий", "бухгалтерия")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT id, email, body, panel_json FROM confirm_reviews "
        "WHERE campaign_id=? ORDER BY id", (КАМПАНИЯ,)).fetchall()

счёт = Counter()
могли_но_не = []
for rid, email, body, pj in строки:
    body = str(body or "")
    try:
        panel = json.loads(pj or "{}")
    except Exception:                                           # noqa: BLE001
        panel = {}
    cont = panel.get("contact") if isinstance(panel.get("contact"), dict) else {}
    имя = str(cont.get("person") or "").strip()
    роль = str(cont.get("role") or "").strip().lower()
    счёт["всего писем"] += 1
    if not имя:
        счёт["1. имени нет в карточке"] += 1
        continue
    счёт["имя в карточке есть"] += 1
    if not _polnoe_imya(имя):
        счёт["2. имя неполное (инициалы)"] += 1
        continue
    if not _imya_soglasuetsya_s_yashchikom(имя, email):
        счёт["3. ящик имени не подтверждает"] += 1
        continue
    if роль in ОБЩИЕ_РОЛИ:
        счёт["4. ящик общий (приёмная/бухгалтерия)"] += 1
        continue
    счёт["5. ИМЯ РАЗРЕШЕНО"] += 1
    if _imennoe_privetstvie(body):
        счёт["   и модель им поздоровалась"] += 1
    else:
        счёт["   а модель им НЕ воспользовалась"] += 1
        могли_но_не.append((rid, имя, email))

всего = max(1, счёт["всего писем"])
print(f"кампания {КАМПАНИЯ}: писем {всего}")
for k in ("всего писем", "1. имени нет в карточке", "имя в карточке есть",
          "2. имя неполное (инициалы)", "3. ящик имени не подтверждает",
          "4. ящик общий (приёмная/бухгалтерия)", "5. ИМЯ РАЗРЕШЕНО",
          "   и модель им поздоровалась",
          "   а модель им НЕ воспользовалась"):
    if k in счёт:
        print(f"  {k:<44} {счёт[k]:>4}  {100.0 * счёт[k] / всего:.0f}%")
print(f"\nмогли поздороваться, но не поздоровались ({len(могли_но_не)}):")
for rid, имя, email in могли_но_не[:15]:
    print(f"  #{rid} {имя!r} -> {email}")
