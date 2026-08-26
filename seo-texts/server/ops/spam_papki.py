# -*- coding: utf-8 -*-
"""Не улетели ли ответы в «Спам»: та же сверка, но по спам-папкам.

INBOX проверен — потерянных ответов нет. Но письмо от получателя могло
уехать в спам, и сторож туда не заходит: он читает INBOX.
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "120"))
СПАМ = re.compile(r"spam|junk|спам|нежелат", re.I)
СВОИ = re.compile(r"kompressor|compressor-store|optic-sort|zernosort|"
                  r"sort-systems|meyer|prokompressor", re.I)
ОБЩИЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru",
         "gmail.com", "rambler.ru", "outlook.com", "hotmail.com", "mail.com"}

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

всего = наших = 0
for м in mb.mailboxes():
    яид = м["mailbox_id"] if isinstance(м, dict) else м
    try:
        папки = mb.folders(яид)
    except Exception as ex:                                   # noqa: BLE001
        print("%-42s папки не читаются: %s" % (яид[:42], str(ex)[:50]))
        continue
    имена = []
    for п in папки:
        имя = п.get("name") if isinstance(п, dict) else str(п)
        показ = п.get("display") if isinstance(п, dict) else имя
        if СПАМ.search(str(имя or "")) or СПАМ.search(str(показ or "")):
            имена.append(имя)
    if not имена:
        continue
    for папка in имена:
        try:
            д = mb.messages(яид, folder=папка, limit=СКОЛЬКО)
        except Exception as ex:                               # noqa: BLE001
            print("%-42s %s: %s" % (яид[:42], папка, str(ex)[:50]))
            continue
        письма = д.get("messages") or []
        всего += len(письма)
        свои_тут = []
        for п in письма:
            отпр = str(п.get("from_addr") or "").lower()
            if not отпр or СВОИ.search(отпр):
                continue
            дом = отпр.rsplit("@", 1)[-1]
            r = c.execute("SELECT id, company_name FROM recipients WHERE email=?",
                          (отпр,)).fetchone()
            if r is None and дом not in ОБЩИЕ:
                строки = c.execute(
                    "SELECT id, inn, company_name FROM recipients "
                    " WHERE lower(domain)=? OR lower(email) LIKE ?",
                    (дом, "%@" + дом)).fetchall()
                инны = {str(x["inn"] or "") for x in строки}
                инны.discard("")
                if строки and len(инны) <= 1:
                    r = строки[0]
            if r is not None:
                свои_тут.append((п, r))
        наших += len(свои_тут)
        print("%-42s %-22s писем %3d | от наших компаний %d"
              % (яид[:42], str(папка)[:22], len(письма), len(свои_тут)))
        for п, r in свои_тут[:6]:
            print("      %s | %-28s | %s" % (str(п.get("date_iso"))[:16],
                                             str(п.get("from_addr"))[:28],
                                             str(r["company_name"])[:30]))
            print("         %s" % str(п.get("subject"))[:80])
print("")
print("итог: писем в спам-папках %d, от наших компаний %d" % (всего, наших))
c.close()
