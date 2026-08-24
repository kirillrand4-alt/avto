# -*- coding: utf-8 -*-
"""Сколько писем в очереди уйдёт по адресам, которые проба ещё не видела.

9 из 14 сегодняшних баунсов — «нет ящика», и приговор в каждом случае
поставила сама отбивка (source=hard-bounce), то есть ДО отправки пробы по
этому адресу не было вовсе. Считаем, сколько таких же непроверенных писем
ждёт отправки прямо сейчас — это завтрашние баунсы.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ПИСЬМА, КОТОРЫЕ ЕЩЁ УЙДУТ ===")
итог = {}
примеры = {}
for р in c.execute(
        "SELECT m.id, m.status, r.email, r.mx_provider "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN ('queued','scheduled','approved','pending')"):
    п = c.execute("SELECT verdict, source FROM addr_probe WHERE email=? "
                  "ORDER BY ts DESC LIMIT 1", (р["email"],)).fetchone()
    к = "ПРОБЫ НЕ БЫЛО" if not п else ("%s [%s]" % (п["verdict"], п["source"] or "-"))
    итог[к] = итог.get(к, 0) + 1
    примеры.setdefault(к, []).append(р["email"])
всего = sum(итог.values())
for к, н in sorted(итог.items(), key=lambda x: -x[1]):
    print("  %-28s %5d  (%s)" % (к, н, ", ".join(примеры[к][:3])[:60]))
print("  ---- всего писем в очереди отправки: %d" % всего)

print("\n=== КАРТОЧКИ ПОДТВЕРЖДЕНИЯ, ЖДУЩИЕ СЛОТА ===")
итог2 = {}
for р in c.execute(
        "SELECT cr.id, cr.status, r.email FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE cr.status IN ('pending','approved')"):
    п = c.execute("SELECT verdict FROM addr_probe WHERE email=? "
                  "ORDER BY ts DESC LIMIT 1", (р["email"],)).fetchone()
    к = "%s / %s" % (р["status"], "ПРОБЫ НЕ БЫЛО" if not п else п["verdict"])
    итог2[к] = итог2.get(к, 0) + 1
for к, н in sorted(итог2.items(), key=lambda x: -x[1]):
    print("  %-40s %5d" % (к, н))

print("\n=== ПРОБА ЗА СУТКИ: СКОЛЬКО АДРЕСОВ ОНА УСПЕВАЕТ ===")
for р in c.execute(
        "SELECT substr(ts,1,10) д, source, COUNT(*) n FROM addr_probe "
        " WHERE ts >= '2026-08-18' GROUP BY 1,2 ORDER BY 1 DESC, n DESC"):
    print("  %s  %-14s %5d" % (р["д"], str(р["source"] or "-"), р["n"]))
