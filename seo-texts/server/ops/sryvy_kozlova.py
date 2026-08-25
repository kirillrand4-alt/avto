# -*- coding: utf-8 -*-
"""Чем именно срываются письма ящика и какой лимит его реально держит."""
import glob
import io
import os
import sqlite3
import sys
from collections import Counter

ЯЩИК = sys.argv[1] if len(sys.argv) > 1 else "a.kozlov@zernosort.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== СРЫВЫ %s ===" % ЯЩИК)
for с in c.execute("SELECT substr(updated_at,1,16) когда, attempt_count п, "
                   "       COALESCE(last_error,'') ош FROM messages "
                   " WHERE mailbox_id=? AND status='failed' "
                   " ORDER BY updated_at DESC LIMIT 12", (ЯЩИК,)):
    print("   %s попыток %s | %s" % (с["когда"], с["п"], с["ош"][:110]))

print("\n=== СРЫВЫ ПО ВСЕМ ЯЩИКАМ ЗА ДВА ДНЯ ===")
for с in c.execute("SELECT mailbox_id я, COUNT(*) n FROM messages "
                   " WHERE status='failed' AND substr(updated_at,1,10) >= '2026-08-24' "
                   " GROUP BY я ORDER BY n DESC LIMIT 10"):
    print("   %-32s %4d" % (с["я"] or "не назначен", с["n"]))
print("   тексты ошибок:")
for к, н in Counter(
        (р[0] or "")[:88] for р in c.execute(
            "SELECT last_error FROM messages WHERE status='failed' "
            "   AND substr(updated_at,1,10) >= '2026-08-24'")).most_common(8):
    print("      %-88s %4d" % (к, н))

print("\n=== КОНФИГ ===")
for п in glob.glob(r"C:\sender\*.yaml") + glob.glob(r"C:\sender\*.yml"):
    print("   %s  %d б" % (п, os.path.getsize(п)))
для_чтения = [п for п in glob.glob(r"C:\sender\*.yaml")]
if для_чтения:
    т = io.open(для_чтения[0], encoding="utf-8", errors="replace").read()
    for блок in ("ramp_curves", "send_limits", "warmup", "auto_send"):
        i = т.find("\n" + блок + ":")
        if i >= 0:
            print("\n--- %s ---" % блок)
            print("\n".join(т[i + 1:i + 900].splitlines()[:20]))
