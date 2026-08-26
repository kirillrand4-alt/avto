# -*- coding: utf-8 -*-
"""Что лежит в ящиках и чего из этого нет в базе как ответа.

Проверка событий показала, что в базе потерянных ответов больше нет. Но
события — это то, что сторож УСПЕЛ разобрать. Если письмо он пропустил
(папка, флаг \\Seen, сбой поллинга), в базе его нет вовсе. Поэтому идём в
сами ящики и сверяем со своей базой.

    python proverit_yashchiki.py [сколько_писем_на_ящик]
"""
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "200"))
ОБЩИЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru",
         "ya.ru", "yandex.com", "gmail.com", "googlemail.com", "rambler.ru",
         "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
         "mail.com", "protonmail.com", "proton.me", "narod.ru"}
СВОИ_ДОМЕНЫ = re.compile(r"kompressor|compressor-store|optic-sort|meyer|"
                         r"prokompressor|ruspro|enger", re.I)

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

# Что база уже знает: Message-ID из detail_json событий.
известные = set()
for r in c.execute("SELECT detail_json FROM events "
                   " WHERE event_type IN ('reply','reply_auto','other',"
                   "'complaint','bounce')"):
    т = r["detail_json"] or ""
    for м in re.finditer(r"<[^<>\s\"]+@[^<>\s\"]+>", т):
        известные.add(м.group(0))
print("Message-ID, известных базе: %d" % len(известные))

свод = Counter()
подозрения = []
ящики = [m["mailbox_id"] if isinstance(m, dict) else m for m in mb.mailboxes()]
print("ящиков: %d" % len(ящики))
for яид in ящики:
    try:
        д = mb.messages(яид, folder="INBOX", limit=СКОЛЬКО)
    except Exception as ex:                                   # noqa: BLE001
        print("   %-42s НЕ ОТКРЫЛСЯ: %s" % (яид, str(ex)[:60]))
        свод["ящик не открылся"] += 1
        continue
    писем = д.get("messages") or []
    свои = чужие = нет_в_базе = 0
    for п in писем:
        отпр = str(п.get("from_addr") or "").lower()
        if not отпр or СВОИ_ДОМЕНЫ.search(отпр):
            свои += 1
            continue
        mid = п.get("message_id") or ""
        if mid and mid in известные:
            continue
        # Наш ли это адресат: по адресу или по корпоративному домену
        дом = отпр.rsplit("@", 1)[-1]
        rec = c.execute("SELECT id, company_name FROM recipients WHERE email=?",
                        (отпр,)).fetchone()
        if rec is None and дом not in ОБЩИЕ:
            строки = c.execute("SELECT id, inn, company_name FROM recipients "
                               " WHERE lower(domain)=? OR lower(email) LIKE ?",
                               (дом, "%@" + дом)).fetchall()
            инны = {str(x["inn"] or "") for x in строки}
            инны.discard("")
            if строки and len(инны) <= 1:
                rec = строки[0]
        if rec is None:
            чужие += 1
            continue
        нет_в_базе += 1
        подозрения.append((яид, п, rec))
    print("   %-42s писем %3d | наших служебных %3d | чужих %3d | НЕ В БАЗЕ %d"
          % (яид, len(писем), свои, чужие, нет_в_базе))

print("")
print("=== письма от наших компаний, которых нет в базе: %d ===" % len(подозрения))
for яид, п, rec in подозрения[:40]:
    print("   %s | %-30s | %-32s" % (str(п.get("date_iso"))[:16],
                                     str(п.get("from_addr"))[:30],
                                     str(rec["company_name"])[:32]))
    print("      тема: %s" % str(п.get("subject"))[:90])
c.close()
