# -*- coding: utf-8 -*-
"""Полная сверка ящиков: сколько писем лежит и сколько база о них знает.

Владелец: «странно что в 2 раза меньше ответов». Проверяем не выборкой:
для каждого ящика берём ВСЕ письма INBOX и сверяем с событиями по паре
(ящик + время ±15 мин + адрес отправителя).
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "1000"))
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

# Все входящие события: ящик -> [(время, адреса из detail)]
события = {}
for r in c.execute(
        "SELECT mailbox_id, event_ts, detail_json, event_type FROM events "
        " WHERE event_type IN ('reply','reply_auto','other','complaint',"
        "'bounce','open','suppress')"):
    я = str(r["mailbox_id"] or "")
    try:
        т = datetime.fromisoformat(str(r["event_ts"]).replace("Z", "+00:00"))
    except Exception:                                         # noqa: BLE001
        continue
    адреса = {a.lower() for a in АДРЕС.findall(r["detail_json"] or "")}
    события.setdefault(я, []).append((т.replace(tzinfo=None), адреса,
                                      r["event_type"]))
print("ящиков в событиях: %d, событий всего: %d"
      % (len(события), sum(len(v) for v in события.values())))

ящики = [м["mailbox_id"] if isinstance(м, dict) else м for м in mb.mailboxes()]
print("ящиков в настройках: %d" % len(ящики))
без_событий = [я for я in ящики if я not in события]
if без_событий:
    print("НЕТ НИ ОДНОГО СОБЫТИЯ У ЯЩИКОВ: %s" % ", ".join(без_событий))

свод = Counter()
пропавшие = []
for яид in ящики:
    try:
        д = mb.messages(яид, folder="INBOX", limit=СКОЛЬКО)
    except Exception as ex:                                   # noqa: BLE001
        print("   %-42s НЕ ОТКРЫЛСЯ: %s" % (яид[:42], str(ex)[:50]))
        continue
    письма = д.get("messages") or []
    наши_соб = события.get(яид, [])
    нет = 0
    for п in письма:
        отпр = str(п.get("from_addr") or "").lower()
        когда = str(п.get("date_iso") or "")
        try:
            т = datetime.fromisoformat(когда).replace(tzinfo=None)
        except Exception:                                     # noqa: BLE001
            т = None
        нашлось = False
        for ст, адреса, _вид in наши_соб:
            if отпр and отпр in адреса:
                нашлось = True
                break
            if т is not None and abs(ст - т) < timedelta(minutes=15):
                нашлось = True
                break
        if not нашлось:
            нет += 1
            пропавшие.append((яид, п))
    свод["писем в INBOX"] += len(письма)
    свод["не сошлось с событиями"] += нет
    print("   %-42s всего в ящике %4d (загружено %3d) | событий %3d | не сошлось %3d"
          % (яид[:42], д.get("total", 0), len(письма), len(наши_соб), нет))

print("")
print("итог: %s" % dict(свод))
print("")
print("=== письма без события (первые 40) ===")
for яид, п in пропавшие[:40]:
    print("   %-34s %s | %-30s | %s"
          % (яид[:34], str(п.get("date_iso"))[:16],
             str(п.get("from_addr"))[:30], str(п.get("subject"))[:52]))
c.close()
