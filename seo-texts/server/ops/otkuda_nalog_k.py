# -*- coding: utf-8 -*-
"""Откуда взялся адрес nalog-k@bk.ru, ушедший как «Автобан».

Автоответ говорит: «Вы обратились на электронный адрес компании Налоговая
Консультация». Значит адрес чужой — бухгалтерия/представитель, а не сама
компания. Смотрим источник в обогащении, а не гадаем.
"""
import sqlite3

АДРЕС = "nalog-k@bk.ru"
s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
s.row_factory = sqlite3.Row
print("=== В РАССЫЛКЕ ===")
for р in s.execute(
        "SELECT id, email, company_name, inn, COALESCE(contact_name,'') кто, "
        "       COALESCE(mx_provider,'') mx FROM recipients WHERE email=?",
        (АДРЕС,)):
    print("   получатель #%s %s | ИНН %s | контакт «%s»"
          % (р["id"], р["company_name"], р["inn"], р["кто"]))
    инн = р["inn"]

e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
кол = [р[1] for р in e.execute("PRAGMA table_info(emails)")]
print("\nemails: %s" % ", ".join(кол))
print("\n=== ЭТОТ АДРЕС В ОБОГАЩЕНИИ ===")
for р in e.execute("SELECT * FROM emails WHERE email=?", (АДРЕС,)):
    for к in р.keys():
        з = str(р[к] or "")
        if з:
            print("   %-18s %s" % (к, з[:150]))

print("\n=== ВСЕ АДРЕСА ЭТОГО ИНН ===")
try:
    for р in e.execute("SELECT * FROM emails WHERE inn=? ORDER BY email", (инн,)):
        поля = {к: str(р[к] or "") for к in р.keys()}
        print("   %-32s источник %-16s %s"
              % (поля.get("email", "")[:32], поля.get("source", "")[:16],
                 (поля.get("source_url") or поля.get("url") or "")[:60]))
except Exception as ex:  # noqa: BLE001
    print("   не вышло: %s" % ex)

print("\n=== КОМПАНИЯ В ОБОГАЩЕНИИ ===")
for т in ("companies", "sites", "site_facts"):
    try:
        ряд = e.execute("SELECT * FROM %s WHERE inn=? LIMIT 1" % т, (инн,)).fetchone()
    except Exception:  # noqa: BLE001
        continue
    if not ряд:
        continue
    print("   [%s]" % т)
    for к in ряд.keys():
        з = str(ряд[к] or "")
        if з and к not in ("html", "text"):
            print("      %-16s %s" % (к, з[:120]))
