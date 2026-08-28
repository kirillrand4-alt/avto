# -*- coding: utf-8 -*-
"""Провести конкретные письма через вотчер по UID.

Сверка нашла их в ящике без события; добор режимом SINCE почему-то не взял.
Берём адресно: тянем сырое письмо по UID и отдаём тому же разбору, что и
штатный опрос — classify + _process_event. Дубля не будет: ключ дедупа
считается из uidvalidity+uid.
"""
import imaplib
import os
import sys

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ЗАДАНИЕ = [("i.lyapin@kompressor-air-trade.ru", ["123", "124"]),
           ("v.ivanov@optic-sort.ru", ["11"])]
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.suppression import Suppression                        # noqa: E402
from sender.imap_watcher import ImapWatcher                       # noqa: E402
from sender.wiring import build_deps                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
w = ImapWatcher(cfg, store, getattr(deps, "suppression", None) or Suppression(store),
                getattr(deps, "leaddesk", None),
                getattr(deps, "reply_pipeline", None))
карта = {mb.mailbox_id: mb for mb in cfg.mailboxes()}
было = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
for ящик, uids in ЗАДАНИЕ:
    mb = карта[ящик]
    пароль = os.getenv(mb.password_env, "")
    im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
    im.login(mb.login, пароль)
    im.select("INBOX")
    typ, d = im.status("INBOX", "(UIDVALIDITY)")
    uv = int(str(d[0]).split("UIDVALIDITY")[-1].strip(" )'\"").split()[0])
    for u in uids:
        typ, data = im.uid("FETCH", u, "(BODY.PEEK[])")
        сырое = None
        for часть in data or []:
            if isinstance(часть, tuple) and часть[1]:
                сырое = часть[1]
                break
        if not сырое:
            print("   %s uid %s: тело не забралось" % (ящик, u)); continue
        ev = w.classify(сырое)
        import dataclasses
        ev = dataclasses.replace(ev, mailbox_id=ящик,
                                 dedup_key="imap:%d:%s:%s" % (uv, u, ev.kind))
        print("   %s uid %s: kind=%s от %s | привязка=%s"
              % (ящик, u, ev.kind, str(ev.from_addr)[:34], ev.recipient_id))
        if КАТИТЬ:
            try:
                w._process_event(ev, ящик)
                print("      проведено")
            except Exception as ex:                               # noqa: BLE001
                print("      ОШИБКА: %s: %s" % (type(ex).__name__, str(ex)[:110]))
    im.logout()
стало = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
print("")
print("событий было %d, стало %d (+%d)" % (было, стало, стало - было))
