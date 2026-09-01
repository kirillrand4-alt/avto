# -*- coding: utf-8 -*-
"""Компании «kc+meyer»: писали по одному направлению, второе не тронуто."""
import io
import json
import sqlite3
from collections import Counter


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
кц, мейер = set(), set()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if z.get("этап") != "итог" or not z.get("ок"):
            continue
        и = цифры(z.get("inn"))
        if not и:
            continue
        (кц if str(z.get("направление")) == "kc" else мейер).add(и)

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
двойные, чисто_мейер = set(), set()
пищевые_кц = set()
for r in e.execute("SELECT inn, division, okved FROM companies"):
    и = цифры(r[0])
    d = str(r[1] or "")
    if "kc" in d and "meyer" in d:
        двойные.add(и)
    elif d == "meyer":
        чисто_мейер.add(и)
    код = str(r[2] or "").strip()
    if d == "kc" and (код.startswith(("01.", "10.", "11.")) or код[:2] in ("01", "10", "11")):
        пищевые_кц.add(и)
e.close()

print("=== КОМПАНИИ «kc+meyer» ===")
print("   всего таких в обогащении: %d" % len(двойные))
print("   писали им по КЦ:          %d" % len(двойные & кц))
print("   писали им по Meyer:       %d" % len(двойные & мейер))
свободны = (двойные & кц) - мейер
print("   писали КЦ, Meyer НЕ писали: %d" % len(свободны))

print("\n=== КЦ-КОМПАНИИ С ПИЩЕВЫМ/АГРО ОКВЭДОМ ===")
print("   помечены kc, но код 01/10/11: %d" % len(пищевые_кц))
print("   из них писали по КЦ:          %d" % len(пищевые_кц & кц))

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
адресов = Counter()
for r in s.execute("SELECT r.inn, COUNT(DISTINCT lower(r.email)) n"
                   "  FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.sent_at IS NOT NULL AND r.inn IS NOT NULL"
                   " GROUP BY r.inn"):
    адресов[цифры(r["inn"] if hasattr(r, "keys") else r[0])] = r[1]
s.close()
кандидаты = свободны | ((пищевые_кц & кц) - мейер)
есть_место = [и for и in кандидаты if адресов.get(и, 0) < 2]
print("\n=== ИТОГ ===")
print("компаний, кому писали КЦ и логично дописать Meyer: %d" % len(кандидаты))
print("из них потолок в 2 адреса не выбран:               %d" % len(есть_место))
