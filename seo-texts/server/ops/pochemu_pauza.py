# -*- coding: utf-8 -*-
"""Что реально держит ящик: ручной потолок, гейт отказов или сам Яндекс."""
import json
import sqlite3
import sys
from collections import Counter

ЯЩИК = sys.argv[1] if len(sys.argv) > 1 else "a.kozlov@zernosort.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== РУЧНОЙ ПОТОЛОК (panel settings send_limits) ===")
for р in c.execute("SELECT key, value FROM panel_settings WHERE key LIKE '%limit%' "
                   "   OR key LIKE '%send%' OR key LIKE '%auto_send%'"):
    print("   %-26s %s" % (р["key"], str(р["value"])[:160]))

print("\n=== СРЫВЫ ЭТОГО ЯЩИКА ===")
for с in c.execute("SELECT substr(updated_at,1,16) когда, attempt_count п, "
                   "       COALESCE(last_error,'') ош FROM messages "
                   " WHERE mailbox_id=? AND status='failed' "
                   " ORDER BY updated_at DESC LIMIT 10", (ЯЩИК,)):
    print("   %s поп.%s %s" % (с["когда"], с["п"], с["ош"][:100]))

print("\n=== СОБЫТИЯ ЯЩИКА (гейт считает по ним) ===")
try:
    for с in c.execute("SELECT type, COUNT(*) n FROM events WHERE mailbox_id=? "
                       " GROUP BY type ORDER BY n DESC", (ЯЩИК,)):
        print("   %-16s %5d" % (с["type"], с["n"]))
    за14 = {с["type"]: с["n"] for с in c.execute(
        "SELECT type, COUNT(*) n FROM events WHERE mailbox_id=? "
        "   AND created_at >= datetime('now','-14 days') GROUP BY type", (ЯЩИК,))}
    отпр, отказ = за14.get("sent", 0), за14.get("bounce", 0)
    print("   за 14 дней: sent %d, bounce %d → %.1f%%"
          % (отпр, отказ, 100.0 * отказ / отпр if отпр else 0.0))
except Exception as e:  # noqa: BLE001
    print("   таблицы events нет: %s" % e)

print("\n=== ЯЩИКИ: РЕАЛЬНАЯ ЗАГРУЗКА СЕГОДНЯ ===")
for с in c.execute("SELECT mailbox_id я, ramp_day р, sent_today с, paused п, "
                   "       COALESCE(pause_reason,'') пр FROM mailbox_state "
                   " ORDER BY с DESC"):
    print("   %-38s рампа %2d сегодня %3d %s%s"
          % (с["я"], с["р"], с["с"], "ПАУЗА " if с["п"] else "", с["пр"][:30]))
