# -*- coding: utf-8 -*-
"""Каким словом помечены отказы в лидах и совпадает ли оно с фильтром панели.

Лид #79 (ЧЗОК) получил reply_kind='отказ', а лид #25 (hoger) —
'not_interested'. Выпадающий список ленты шлёт в API ключ 'not_interested'.
Если в базе лежит русское слово, фильтр «отказ» не найдёт ничего.
"""
import io
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== reply_kind В ЛИДАХ ===")
for р in c.execute(
        "SELECT COALESCE(reply_kind,'(пусто)') k, COUNT(*) n, MIN(id) a, "
        "MAX(id) b, MAX(created_at) t FROM leads GROUP BY 1 ORDER BY n DESC"):
    print("  %-16s %4d шт   лиды #%s..#%s   последний %s"
          % (р["k"], р["n"], р["a"], р["b"], str(р["t"])[:16]))

print("\n=== status В ЛИДАХ ===")
for р in c.execute(
        "SELECT COALESCE(status,'(пусто)') s, COUNT(*) n FROM leads "
        "GROUP BY 1 ORDER BY n DESC"):
    print("  %-16s %4d" % (р["s"], р["n"]))

print("\n=== ЧТО КЛАДЁТ В ТЕГ БОЕВОЙ imap_watcher.py ===")
т = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8").read()
for м in re.finditer(r"^.*tags\s*=.*$", т, re.M):
    н = т[:м.start()].count("\n") + 1
    print("  %-5d %s" % (н, м.group(0).strip()))

print("\n=== КАК ФИЛЬТРУЕТ store.leads_list ===")
s = io.open(r"C:\sender\sender\store.py", encoding="utf-8").read()
и = s.find("def leads_list")
if и >= 0:
    for строка in s[и:и + 2600].split("\n"):
        if "reply_kind" in строка or "def leads_list" in строка:
            print("  %s" % строка.strip())

print("\n=== СВЕЖИЕ ЛИДЫ (последние 12) ===")
кол = [к[1] for к in c.execute("PRAGMA table_info(leads)")]
поля = [п for п in ("id", "email", "status", "reply_kind", "company_name",
                    "created_at", "v_bitrix") if п in кол]
for р in c.execute("SELECT %s FROM leads ORDER BY id DESC LIMIT 12"
                   % ", ".join(поля)):
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:34]) for п in поля
                            if р[п] not in (None, "")))
