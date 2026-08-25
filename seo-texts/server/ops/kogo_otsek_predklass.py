# -*- coding: utf-8 -*-
"""Кого предклассификатор отсеял в блоке КЦ — и не режет ли он своих.

Тревога: среди отсеянных «АО РИФАР» (завод алюминиевых радиаторов) — там
цех, компрессор нужен наверняка. Если так режет пачками, блок потеряет
годные компании молча. Смотрим ОКВЭД отсеянных: доля обрабатывающих
производств (коды 10-33) и строительства — это наш профиль по определению.
"""
import io
import json
import os
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 900000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]

отсеяны = []
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") == "предкласс_отсев" and з.get("направление") == "kc":
        отсеяны.append((str(з.get("inn") or ""), з.get("имя") or ""))
print("отсеяно предклассом в блоке КЦ (по хвосту журнала): %d" % len(отсеяны))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
классы = Counter()
примеры = {}
for инн, имя in отсеяны:
    р = c.execute("SELECT okved FROM recipients WHERE inn=? LIMIT 1",
                  (инн,)).fetchone()
    о = str((р["okved"] if р else "") or "")
    код = о.split()[0] if о else ""
    гр = код.split(".")[0] if код else ""
    try:
        н = int(гр)
    except ValueError:
        н = -1
    if 10 <= н <= 33:
        к = "ОБРАБАТЫВАЮЩЕЕ ПРОИЗВОДСТВО (наш профиль)"
    elif н in (41, 42, 43):
        к = "строительство (наш профиль)"
    elif н in (45, 46, 47):
        к = "торговля"
    elif н in (49, 50, 51, 52, 53):
        к = "транспорт и склад"
    elif н in (1, 2, 3):
        к = "сельское хозяйство"
    elif н == -1:
        к = "ОКВЭД неизвестен"
    else:
        к = "прочее (%s)" % (гр or "?")
    классы[к] += 1
    примеры.setdefault(к, []).append("%s [%s]" % (имя[:38], о[:34]))

print("\n=== ЧТО ЗА КОМПАНИИ ОТСЕЯНЫ ===")
свой = sum(н for к, н in классы.items() if "наш профиль" in к)
for к, н in классы.most_common(6):
    print("   %-46s %5d  (%4.1f%%)" % (к, н, 100.0 * н / max(1, len(отсеяны))))
print("   %-46s %5d  (%4.1f%%)"
      % ("... прочие классы", len(отсеяны) - sum(н for _к, н in классы.most_common(6)),
         100.0 * (len(отсеяны) - sum(н for _к, н in классы.most_common(6)))
         / max(1, len(отсеяны))))
print("\n   ИЗ НИХ НАШ ПРОФИЛЬ (производство + стройка): %d из %d = %.1f%%"
      % (свой, len(отсеяны), 100.0 * свой / max(1, len(отсеяны))))
print("\n=== ПРИМЕРЫ ИЗ НАШЕГО ПРОФИЛЯ ===")
for к in ("ОБРАБАТЫВАЮЩЕЕ ПРОИЗВОДСТВО (наш профиль)", "строительство (наш профиль)"):
    for п in примеры.get(к, [])[:6]:
        print("   %s" % п)
