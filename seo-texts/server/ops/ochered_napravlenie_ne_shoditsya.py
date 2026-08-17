# -*- coding: utf-8 -*-
"""Письма, где направление письма спорит с направлением карточки.

Владелец на карточке #527 («Кубань-Вино»): в панели снизу написано «наше
направление: Компрессор Центр (по метке базы)», а письмо и ящик - Meyer,
про сортировку винограда. «Писали +мейер когда оно кц».

Спорят два независимых источника:
  * НАПРАВЛЕНИЕ ПИСЬМА - panel.letter_division, а у старых писем его нет, и
    тогда ConfirmSend.letter_division достаёт его из лексики самого текста;
  * НАПРАВЛЕНИЕ КАРТОЧКИ - panel.company.division, оно же «метка базы»,
    которую оператор читает в карточке и по которой принимает решение.

Пока они спорят, оператор подтверждает одно, а уходит другое. Считаем,
сколько таких писем в очереди, и печатаем их списком - чинить надо
перегенерацией, а для этого нужен точный список.

    python zapusk_svoego_skripta.py ops/ochered_napravlenie_ne_shoditsya.py
"""
import io
import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ИМЯ = "OCHERED-NAPRAVLENIE-SPOR.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

строки = store.confirm_list(limit=100000)
счёт = Counter()
спорные = []
for r in строки:
    if (r.get("kind") or "outbound") == "reply":
        continue
    счёт["всего писем"] += 1
    panel = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    поле = str((panel or {}).get("letter_division") or "").strip().lower()
    письмо = str(cs.letter_division(r) or "").strip().lower()
    comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
    карточка = str(comp.get("division") or "").strip().lower()
    счёт["поле letter_division заполнено" if поле else
         "поле letter_division ПУСТО"] += 1
    if not письмо or not карточка:
        счёт["сравнить не с чем"] += 1
        continue
    if карточка in ("kc+meyer", "meyer+kc"):
        счёт["карточка составная - спора нет"] += 1
        continue
    if письмо == карточка:
        счёт["сходится"] += 1
        continue
    счёт[f"СПОР: письмо {письмо}, карточка {карточка}"] += 1
    счёт[f"  из них статус {r.get('status')}"] += 1
    спорные.append({
        "id": r.get("id"), "статус": r.get("status"),
        "кампания": r.get("campaign_id"), "email": r.get("email"),
        "фирма": (comp.get("name") or "")[:52],
        "письмо": письмо, "карточка": карточка,
        "поле": поле or "нет", "тема": (r.get("subject") or "")[:70]})

С = ["# Спор направлений в очереди", "",
     "Направление письма (поле генератора, иначе лексика текста) против",
     "направления карточки (метка базы, её читает оператор).", ""]
for k, n in счёт.most_common():
    С.append(f"- {k}: **{n}**")
С += ["", f"## Список спорных ({len(спорные)})", ""]
for s in спорные:
    С.append(f"- **#{s['id']}** {s['статус']} камп.{s['кампания']} · "
             f"{s['фирма']} · {s['email']}")
    С.append(f"  письмо **{s['письмо']}** против карточки **{s['карточка']}** "
             f"(поле letter_division: {s['поле']})")
    С.append(f"  тема: {s['тема']}")

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

for k, n in счёт.most_common():
    print(f"  {k:<46} {n}")
print(f"\nспорных писем: {len(спорные)}")
for s in спорные[:15]:
    print(f"  #{s['id']} {s['статус']:<9} {s['письмо']:<6} vs "
          f"{s['карточка']:<6} {s['фирма'][:40]}")
