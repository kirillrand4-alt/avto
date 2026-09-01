# -*- coding: utf-8 -*-
"""Сколько компаний заперты тем, что им уже писали по КЦ, а нужны Meyer."""
import io
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
по_инн = {}
перестановки = {}
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        и = цифры(z.get("inn"))
        if not и or z.get("этап") != "итог":
            continue
        по_инн.setdefault(и, []).append(
            (str(z.get("направление") or ""), bool(z.get("ок"))))
        б = str(z.get("брак") or "")
        if "переставить на meyer" in б:
            перестановки[и] = "кц→meyer"
        elif "переставить на kc" in б:
            перестановки.setdefault(и, "meyer→кц")

писали_кц = {и for и, сп in по_инн.items()
             if any(н == "kc" and ок for н, ок in сп)}
писали_мейер = {и for и, сп in по_инн.items()
                if any(н == "meyer" and ок for н, ок in сп)}
print("=== ПО ЖУРНАЛУ ГЕНЕРАЦИИ ===")
print("   фирм с готовым письмом КЦ:            %d" % len(писали_кц))
print("   фирм с готовым письмом Meyer:         %d" % len(писали_мейер))
print("   фирм, где есть и то и другое:         %d"
      % len(писали_кц & писали_мейер))
print("   линза просила переставить на meyer:   %d"
      % sum(1 for v in перестановки.values() if v == "кц→meyer"))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
мейеровские = {цифры(r[0]) for r in e.execute(
    "SELECT inn FROM companies WHERE division LIKE '%meyer%'")}
e.close()
запертые = писали_кц & мейеровские - писали_мейер
print("\n=== ЗАПЕРТЫЕ ===")
print("   писали КЦ, а по обогащению это Meyer: %d" % len(запертые))

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
адресов = Counter()
for r in s.execute("SELECT r.inn, COUNT(DISTINCT lower(r.email)) n"
                   "  FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.sent_at IS NOT NULL AND r.inn IS NOT NULL"
                   " GROUP BY r.inn"):
    адресов[цифры(r["inn"])] = r["n"]
s.close()
свободен = [и for и in запертые if адресов.get(и, 0) < 2]
занят = [и for и in запертые if адресов.get(и, 0) >= 2]
print("   из них потолок компании (2 адреса) НЕ выбран: %d" % len(свободен))
print("   потолок выбран, заслон остановит:            %d" % len(занят))

print("\n=== ИТОГ ===")
print("реально можно дописать по Meyer, не трогая заслонов: %d фирм"
      % len(свободен))
print("им мешает только резюм по ИНН в журнале — он не смотрит направление")
