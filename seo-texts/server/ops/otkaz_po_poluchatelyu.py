# -*- coding: utf-8 -*-
"""Отказы Яндекса — зависят ли они от почтовика ПОЛУЧАТЕЛЯ.

Все мейеровские ящики яндексовые, а две трети базы — mail.ru. Если отказы
липнут именно к mail.ru-получателям, дело в несовпадении почтовиков, а не
в тексте письма, и лечится это маршрутом, а не порогом паузы.
"""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
МЕЙЕР = ("zernosort", "optic-sort", "sort-systems")


def напр(я):
    return "Meyer" if any(д in (я or "") for д in МЕЙЕР) else "КЦ"


def почтовик(адрес):
    д = str(адрес or "").split("@")[-1].lower()
    if д in ("mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru"):
        return "mail.ru"
    if д in ("yandex.ru", "ya.ru", "yandex.com"):
        return "yandex"
    return "свой домен"


таб = defaultdict(Counter)
for р in c.execute(
        "SELECT m.status, COALESCE(m.last_error,'') ош, m.mailbox_id я, r.email "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN ('sent','failed') "
        "   AND substr(COALESCE(m.sent_at,m.updated_at),1,10) >= '2026-08-20'"):
    к = (напр(р["я"]), почтовик(р["email"]))
    if р["status"] == "sent":
        таб[к]["ушло"] += 1
    elif "suspicion of SPAM" in р["ош"]:
        таб[к]["отказ по спаму"] += 1
    else:
        таб[к]["прочий срыв"] += 1

print("%-8s %-12s %7s %7s %8s" % ("направл", "почтовик", "ушло", "отказ", "доля"))
for к in sorted(таб):
    ст = таб[к]
    всего = ст["ушло"] + ст["отказ по спаму"]
    print("%-8s %-12s %7d %7d %7.1f%%"
          % (к[0], к[1], ст["ушло"], ст["отказ по спаму"],
             100.0 * ст["отказ по спаму"] / всего if всего else 0.0))

print("\n=== ЧЬИ ЯЩИКИ ШЛЮТ, КОГДА ПОЛУЧАТЕЛЬ mail.ru ===")
for р in c.execute(
        "SELECT m.mailbox_id я, m.status, COUNT(*) n FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE (r.email LIKE '%@mail.ru' OR r.email LIKE '%@list.ru' "
        "        OR r.email LIKE '%@bk.ru' OR r.email LIKE '%@inbox.ru') "
        "   AND m.status IN ('sent','failed') "
        "   AND substr(COALESCE(m.sent_at,m.updated_at),1,10) >= '2026-08-24' "
        " GROUP BY я, m.status ORDER BY n DESC LIMIT 14"):
    print("   %-38s %-8s %4d" % (р["я"], р["status"], р["n"]))
