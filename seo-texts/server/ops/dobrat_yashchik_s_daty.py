# -*- coding: utf-8 -*-
"""Штатный разбор ящика с даты (poll_once SINCE, \\Seen не трогаем): письма,
которые сборщик пропустил, потому что их открыли руками раньше него (берёт
только UNSEEN). Дедуп событий защищает от повторов. Показывает флаги писем.

    dobrat_yashchik_s_daty.py <ящик> <13-Oct-2026> [primenit]
"""
import os
import re
import imaplib
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
ЯЩ, С = sys.argv[1], sys.argv[2]
cfg = Config.load(r"C:\sender\sender.yaml")
mb = next(m for m in cfg.mailboxes() if m.mailbox_id == ЯЩ)
im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
im.login(mb.login, os.getenv(mb.password_env, ""))
im.select("INBOX", readonly=True)
вс = (im.uid("SEARCH", None, "SINCE", С)[1][0] or b"").split()
print("писем с даты: %d" % len(вс))
if вс and "primenit" not in sys.argv:
    for ч in im.uid("FETCH", b",".join(вс), "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")[1] or []:
        if isinstance(ч, tuple):
            print("  %s | %s" % (re.sub(r"\s+", " ", ч[0].decode(errors="replace"))[:80],
                                 re.sub(r"\s+", " ", ч[1].decode(errors="replace"))[:110]))
im.logout()
if "primenit" not in sys.argv:
    print("=== ДОБОР ЯЩИКА: ВХОЛОСТУЮ ===")
    sys.exit(0)
from sender.imap_watcher import ImapWatcher  # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сторож = ImapWatcher(cfg, store, Suppression(store), reply_desk=LeadDesk(cfg, store))
события = сторож.poll_once(ЯЩ, criteria=("SINCE", С), mark_seen=False, batch=1000)
from collections import Counter  # noqa: E402
print("по видам: %s" % dict(Counter(e.kind for e in события)))
for e in события:
    if e.kind in ("reply", "other"):
        print("событие: %s от %s, получатель %s" % (e.kind, e.from_addr, e.recipient_id))
print("разобрано: %d" % len(события))
print("=== ДОБОР ЯЩИКА: ПРИМЕНЕНО ===")
