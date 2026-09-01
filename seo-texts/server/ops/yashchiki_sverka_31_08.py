# -*- coding: utf-8 -*-
"""Только чтение: где заданы ящики отправки и чем новые отличаются от старых."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ТАБЛИЦЫ ПРО ЯЩИКИ ===")
for т in ("mailbox_state", "mailbox_overrides", "warmup_state"):
    try:
        кол = [r["name"] for r in s.execute("PRAGMA table_info(%s)" % т)]
        n = s.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("  %-20s %4d строк | %s" % (т, n, ", ".join(кол)))
    except Exception as ex:
        print("  %-20s %s" % (т, str(ex)[:60]))

print("\n=== ЯЩИКИ ИЗ КОНФИГА ===")
for ключ in ("mailboxes", "smtp.mailboxes", "sender.mailboxes", "accounts"):
    try:
        v = cfg.get(ключ)
        if v:
            print("  ключ %s: тип %s, элементов %s"
                  % (ключ, type(v).__name__, len(v) if hasattr(v, "__len__") else "?"))
            if isinstance(v, list) and v:
                print("    поля первого: %s" % sorted(v[0].keys()) if isinstance(v[0], dict) else v[0])
            break
    except Exception as ex:
        print("  %s -> %s" % (ключ, str(ex)[:60]))

print("\n=== mailbox_state ЦЕЛИКОМ ===")
try:
    ряды = list(s.execute("SELECT * FROM mailbox_state"))
    if ряды:
        кол = list(ряды[0].keys())
        print("  " + " | ".join(кол))
        for р in ряды:
            print("  " + " | ".join(str(р[k])[:24] for k in кол))
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== warmup_state ЦЕЛИКОМ ===")
try:
    ряды = list(s.execute("SELECT * FROM warmup_state"))
    if ряды:
        кол = list(ряды[0].keys())
        print("  " + " | ".join(кол))
        for р in ряды:
            print("  " + " | ".join(str(р[k])[:22] for k in кол))
    else:
        print("  пусто")
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ИТОГ: ОТПРАВКИ И ОТБИВКИ ПО ЯЩИКАМ за 7 дней ===")
try:
    for р in s.execute(
            "SELECT mailbox, COUNT(*) n,"
            " SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) ok,"
            " SUM(CASE WHEN status<>'sent' THEN 1 ELSE 0 END) плохо,"
            " MIN(substr(created_at,1,10)) первый,"
            " MAX(substr(created_at,1,10)) последний"
            " FROM send_log WHERE created_at >= date('now','-7 day')"
            " GROUP BY mailbox ORDER BY n DESC"):
        print("  %-42s всего %5d | ок %5d | иное %4d | %s..%s"
              % (str(р["mailbox"])[:42], р["n"], р["ok"] or 0, р["плохо"] or 0,
                 р["первый"], р["последний"]))
except Exception as ex:
    print("  send_log: %s" % str(ex)[:120])
