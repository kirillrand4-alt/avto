# -*- coding: utf-8 -*-
"""Откуда в письме взялось имя: показать карточку письма как она есть.

Дамп ops/partiya_pokazat_pisma.py читал имя контакта из panel['company'] и
на всех шести письмах напечатал «нет имени» - при том что в трёх письмах
стоит именное приветствие. Одно из двух: либо модель имя выдумала (тогда
это брак, и срочный), либо имя лежит в другом ключе панели. Гадать нельзя,
поэтому печатаем ключи панели целиком и все места, где может лежать имя,
роль ящика и адрес.

    python zapusk_svoego_skripta.py ops/partiya_kartochka_pisma.py 1280 1285
"""
import io
import json
import os
import sqlite3
import sys
import urllib.request

БАЗА = r"C:\sender\sender.db"
ИМЯ = "KARTOCHKA-PISMA.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
ОТ = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
ДО = int(sys.argv[2]) if len(sys.argv) > 2 else 1285

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

С = []


def п(s=""):
    С.append(s)


def найти(узел, ключи, путь="panel"):
    """Все места в панели, где лежит один из ключей. Панель вложенная."""
    найдено = []
    if isinstance(узел, dict):
        for k, v in узел.items():
            п_ = f"{путь}.{k}"
            if k in ключи and not isinstance(v, (dict, list)):
                найдено.append((п_, v))
            найдено += найти(v, ключи, п_)
    elif isinstance(узел, list):
        for i, v in enumerate(узел[:5]):
            найдено += найти(v, ключи, f"{путь}[{i}]")
    return найдено


КЛЮЧИ = {"contact_name", "person", "role", "email", "contact_source",
         "contact_source_url", "division", "imya_ok", "fio", "name"}

строки = list(conn.execute(
    "SELECT id, campaign_id, email, subject, panel_json FROM confirm_reviews "
    "WHERE id BETWEEN ? AND ? ORDER BY id", (ОТ, ДО)))

п(f"# Карточки писем #{ОТ}-#{ДО}: откуда имя")
п()
for r in строки:
    try:
        panel = json.loads(r["panel_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        panel = {}
    п(f"## #{r['id']} камп.{r['campaign_id']} {r['email']}")
    п()
    п(f"тема: {r['subject']}")
    п()
    п(f"ключи панели верхнего уровня: {sorted(panel.keys())}")
    п()
    for путь, знач in найти(panel, КЛЮЧИ):
        п(f"- `{путь}` = {знач!r}")
    п()

# Полная панель одного письма - чтобы видеть форму целиком.
if строки:
    п("## Панель первого письма целиком")
    п()
    п("```json")
    try:
        п(json.dumps(json.loads(строки[0]["panel_json"] or "{}"),
                     ensure_ascii=False, indent=1)[:12000])
    except Exception as ex:                                    # noqa: BLE001
        п(f"панель не разобралась: {ex}")
    п("```")

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
except Exception as ex:                                        # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])
print(f"писем разобрано: {len(строки)}")
