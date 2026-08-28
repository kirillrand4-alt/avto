# -*- coding: utf-8 -*-
"""Порядковый номер против UID: совпадают ли они в ящиках."""
import imaplib
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
for mb in cfg.mailboxes():
    ящик = mb.mailbox_id
    пароль = os.getenv(mb.password_env, "")
    if not пароль:
        continue
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=20)
        im.login(mb.login, пароль)
        im.select("INBOX")
        typ, d = im.status("INBOX", "(UIDVALIDITY)")
        uv = int(str(d[0]).split("UIDVALIDITY")[-1].strip(" )'\"").split()[0])
        # порядковые номера всех писем
        typ, s = im.search(None, "ALL")
        seqs = [x.decode() for x in (s[0] or b"").split()]
        # их же UID
        typ, u = im.uid("SEARCH", None, "ALL")
        uids = [x.decode() for x in (u[0] or b"").split()]
        расх = sum(1 for a, b in zip(seqs, uids) if a != b)
        # сколько ключей событий этого ящика попадают в диапазон seq
        with store._lock:
            n = store._conn.execute(
                "SELECT COUNT(*) FROM events WHERE mailbox_id=? "
                "  AND dedup_key LIKE ?", (ящик, "imap:%d:%%" % uv)).fetchone()[0]
        print("%-38s писем %3d | seq==uid у %3d, расходится %3d | событий с этим uidvalidity %3d"
              % (ящик[:38], len(seqs), len(seqs) - расх, расх, n))
        im.logout()
    except Exception as ex:                                       # noqa: BLE001
        print("%-38s ошибка: %s" % (ящик[:38], str(ex)[:60]))
