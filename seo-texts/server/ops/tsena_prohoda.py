# -*- coding: utf-8 -*-
"""Во что обойдётся пробе читать одобренные карточки каждый тик."""
import io
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT status, COUNT(*) n, "
        "       SUM(LENGTH(COALESCE(body,'')) + LENGTH(COALESCE(subject,''))) б "
        "  FROM confirm_reviews GROUP BY status ORDER BY б DESC"):
    print("  %-14s %5d карточек, текста %.1f МБ"
          % (р["status"], р["n"], (р["б"] or 0) / 1048576.0))

print("\n=== НАСТРОЙКИ ПРОБЫ ===")
try:
    import yaml
    к = yaml.safe_load(io.open(r"C:\sender\config.yaml", encoding="utf-8"))
    ap = (к or {}).get("addr_probe", {})
    for кл in ("interval_sec", "batch", "per_domain", "pause_sec", "ttl_days"):
        print("  %-14s %s" % (кл, ap.get(кл, "(по умолчанию)")))
except Exception as e:  # noqa: BLE001
    print("  конфиг не прочитан: %s" % e)

print("\n=== ВКЛЮЧЕНА ЛИ ПРОБА ===")
for р in c.execute("SELECT key, value FROM settings WHERE key LIKE '%probe%'"):
    print("  %s = %s" % (р["key"], р["value"]))
