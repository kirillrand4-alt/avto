# -*- coding: utf-8 -*-
"""Только чтение: где сейчас ответ Чистозерья. Важное в конце."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def поля(т):
    return [р["name"] for р in c.execute("PRAGMA table_info(%s)" % т)]


print("=== СХЕМЫ ===")
for т in ("recipients", "leads"):
    print("  %s: %s" % (т, ", ".join(поля(т))))

print("\n=== enrich: компания и почты ===")
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
for р in e.execute("SELECT inn, name, site, region, revenue_rub, okved"
                   " FROM companies WHERE name LIKE '%ИСТОЗЕРЬ%'"
                   " OR site LIKE '%chistozer%'"):
    print("  %s | %s | %s | %s | %s"
          % (р["inn"], р["name"], р["site"], р["region"], str(р["okved"])[:30]))
for р in e.execute("SELECT inn, email, source FROM emails"
                   " WHERE email LIKE '%chistozer%' OR email LIKE '%gnezdalova%'"
                   " LIMIT 12"):
    print("  почта: %s %s (%s)" % (р["inn"], р["email"], р["source"]))

print("\n=== ЛЕНТА: ЧТО ЕСТЬ ПРО ЧИСТОЗЕРЬЕ ===")


def искать(таблица, шаблоны):
    пп = поля(таблица)
    текст = [п for п in пп if п not in ("id",)]
    усл = " OR ".join("IFNULL(%s,'') LIKE ?" % п for п in текст)
    ряды = []
    for ш in шаблоны:
        try:
            ряды += [dict(р) for р in c.execute(
                "SELECT * FROM %s WHERE %s" % (таблица, усл), [ш] * len(текст))]
        except sqlite3.OperationalError as ex:
            print("  %s: %s" % (таблица, ex))
            return []
    return ряды


ШАБЛОНЫ = ("%chistozer%", "%истозерь%", "%ИСТОЗЕРЬ%", "%gnezdalova%",
           "%Гнезд%")
for т in ("recipients", "leads"):
    ряды = искать(т, ШАБЛОНЫ)
    print("\n  --- %s: найдено %d ---" % (т, len(ряды)))
    for р in ряды[:6]:
        print("   " + str({к: v for к, v in р.items()
                           if v not in (None, "", 0)})[:700])

print("\n=== СОБЫТИЯ 07.09 ТИПА reply ===")
for р in c.execute(
        "SELECT id, event_type, recipient_id, message_id, mailbox_id,"
        " event_ts, substr(IFNULL(detail_json,''),1,220) d FROM events"
        " WHERE event_type IN ('reply','reply_auto','other')"
        " AND IFNULL(event_ts, created_at) >= '2026-09-06'"
        " ORDER BY id DESC LIMIT 25"):
    print("  %s %s r=%s m=%s %s %s | %s"
          % (р["id"], р["event_type"], р["recipient_id"], р["message_id"],
             р["mailbox_id"], р["event_ts"], р["d"]))
