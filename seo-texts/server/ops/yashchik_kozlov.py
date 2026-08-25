# -*- coding: utf-8 -*-
"""Почему a.kozlov@zernosort.ru отправляет по одному письму и встаёт на паузу.

Смотрим не догадкой, а по базе: состояние ящика, причина паузы, сколько
писем ему вообще досталось за последние дни, отказы и жалобы — и рампу
из конфига, которая задаёт «можно сегодня».
"""
import io
import sqlite3
import sys
from collections import Counter

ЯЩИК = sys.argv[1] if len(sys.argv) > 1 else "a.kozlov@zernosort.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

кол = [р[1] for р in c.execute("PRAGMA table_info(mailbox_state)")]
print("mailbox_state: %s" % ", ".join(кол))
р = c.execute("SELECT * FROM mailbox_state WHERE mailbox_id=?", (ЯЩИК,)).fetchone()
if р:
    for к in р.keys():
        print("   %-18s %s" % (к, р[к]))
else:
    print("   строки нет — ящик ни разу не отправлял")

print("\n=== СОСЕДИ ПО ДОМЕНУ zernosort.ru ===")
for с in c.execute("SELECT mailbox_id, ramp_day, daily_limit, sent_today, "
                   "       sent_total, paused, COALESCE(pause_reason,'') pr "
                   "  FROM mailbox_state WHERE mailbox_id LIKE '%zernosort%'"):
    print("   %-30s рампа %2d лимит %3d сегодня %3d всего %4d пауза %s %s"
          % (с["mailbox_id"], с["ramp_day"], с["daily_limit"], с["sent_today"],
             с["sent_total"], с["paused"], с["pr"][:40]))

print("\n=== ПИСЬМА ЭТОГО ЯЩИКА ПО ДНЯМ ===")
for с in c.execute(
        "SELECT substr(COALESCE(sent_at,scheduled_at),1,10) д, status, COUNT(*) n "
        "  FROM messages WHERE mailbox_id=? GROUP BY д, status "
        " ORDER BY д DESC LIMIT 12", (ЯЩИК,)):
    print("   %s  %-12s %4d" % (с["д"], с["status"], с["n"]))

print("\n=== СКОЛЬКО ПИСЕМ В ОЧЕРЕДИ ЖДЁТ ИМЕННО ЕГО ===")
for с in c.execute("SELECT COALESCE(mailbox_id,'не назначен') я, COUNT(*) n "
                   "  FROM messages WHERE status IN ('scheduled','sending') "
                   " GROUP BY я ORDER BY n DESC LIMIT 12"):
    print("   %-32s %4d" % (с["я"], с["n"]))

try:
    т = io.open(r"C:\sender\config.yaml", encoding="utf-8").read()
    for блок in ("ramp_curves", "send_limits", "warmup"):
        i = т.find(блок + ":")
        if i >= 0:
            print("\n=== config.yaml: %s ===" % блок)
            print("\n".join(т[i:i + 700].splitlines()[:18]))
except Exception as e:  # noqa: BLE001
    print("конфиг не прочитан: %s" % e)
