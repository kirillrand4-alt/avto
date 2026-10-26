# -*- coding: utf-8 -*-
"""Сверка: письма во ВХОДЯЩИХ ящиков после момента T против записанных событий.
Только чтение: MailBrowser (select readonly, BODY.PEEK — флаги не трогаем).
    vhodyashchie_v_yashchikah.py <T UTC, напр. 2026-10-26T10:45>"""
import io
import os
import sqlite3
import sys
from datetime import datetime, timezone

import requests

BASE = r"C:\sender"
sys.path.insert(0, BASE)
for line in io.open(os.path.join(BASE, "panel.env"), encoding="utf-8", errors="replace").read().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))
from sender.config import Config            # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402

T = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
cfg = Config.load(os.path.join(BASE, "sender.yaml"))
mbr = MailBrowser(cfg)
c = sqlite3.connect(os.path.join(BASE, "sender.db"), timeout=60)
известные = {r[0].strip() for r in c.execute("SELECT rfc_msgid FROM events WHERE rfc_msgid IS NOT NULL AND event_ts >= date('now','-2 days')")}
вых, всего, новых, сбоев = [], 0, 0, 0
for mb in cfg.mailboxes():
    try:
        р = mbr.messages(mb.mailbox_id, folder="INBOX", limit=40)
    except Exception as ex:  # noqa: BLE001
        сбоев += 1
        вых.append("%s: сбой чтения %s" % (mb.mailbox_id, str(ex)[:80]))
        continue
    for m in р.get("messages") or р.get("items") or []:
        try:
            д = datetime.fromisoformat(m.get("date_iso") or "")
        except ValueError:
            continue
        if д.tzinfo is None:
            д = д.replace(tzinfo=timezone.utc)
        if д < T:
            continue
        всего += 1
        mid = (m.get("message_id") or "").strip().strip("<>")
        записано = any(mid and mid in к for к in известные)
        if not записано:
            новых += 1
        вых.append("%s %s | %s | %s | %s" % ("ЗАПИСАНО " if записано else "НЕТ В БАЗЕ", д.astimezone(timezone.utc).strftime("%H:%M"),
                                            mb.mailbox_id, m.get("from_addr"), (m.get("subject") or "")[:70]))
т = "писем во входящих после %s UTC: %d, из них нет в базе: %d, ящиков со сбоем чтения: %d\n" % (sys.argv[1], всего, новых, сбоев) + "\n".join(вых)
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/vhodyashchie-v-yashchikah.txt",
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
print(т[:6000])
