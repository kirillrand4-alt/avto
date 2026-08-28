# -*- coding: utf-8 -*-
"""Точная сверка: каждое письмо ящика против события по Message-ID.

Прежняя сверка сопоставляла по «ящик + время ±15 мин + адрес» и давала
ложные срабатывания (Содружество). Message-ID уникален, совпадение точное.
Смотрим INBOX и папку спама.
"""
import imaplib
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

ПАПКИ = ["INBOX", "Spam", "Junk", "INBOX.Spam", "&BCEEPwQwBDw-"]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
итог = Counter()
пропало = []
for mb in cfg.mailboxes():
    ящик = mb.mailbox_id
    пароль = os.getenv(mb.password_env, "")
    if not пароль:
        continue
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
        im.login(mb.login, пароль)
    except Exception as ex:                                       # noqa: BLE001
        print("%-34s вход не вышел: %s" % (ящик[:34], str(ex)[:50]))
        continue
    typ, спис = im.list()
    доступные = []
    for стр in (спис or []):
        м = re.search(rb'"([^"]+)"$', стр if isinstance(стр, bytes) else b"")
        if м:
            доступные.append(м.group(1).decode())
    for папка in ПАПКИ:
        if папка != "INBOX" and папка not in доступные:
            continue
        try:
            typ, _ = im.select(папка, readonly=True)
            if typ != "OK":
                continue
            typ, d = im.uid("SEARCH", None, "ALL")
            uids = (d[0] or b"").split()
            if not uids:
                continue
            нет = 0
            for u in uids:
                typ, md = im.uid("FETCH", u, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
                сыр = b""
                for ч in md or []:
                    if isinstance(ч, tuple) and ч[1]:
                        сыр = ч[1]
                        break
                мид = re.search(rb"(?i)message-id:\s*(<[^>]+>)", сыр)
                if not мид:
                    continue
                мид = мид.group(1).decode(errors="replace")
                with store._lock:
                    есть = store._conn.execute(
                        "SELECT 1 FROM events WHERE detail_json LIKE ? LIMIT 1",
                        ("%" + мид + "%",)).fetchone()
                итог["писем всего"] += 1
                if есть:
                    итог["есть событие"] += 1
                else:
                    нет += 1
                    итог["БЕЗ СОБЫТИЯ"] += 1
                    от = re.search(rb"(?i)^from:\s*(.+)$", сыр, re.M)
                    тем = re.search(rb"(?i)^subject:\s*(.+)$", сыр, re.M)
                    пропало.append((ящик, папка, u.decode(),
                                    (от.group(1).decode(errors="replace")[:40]
                                     if от else "?"),
                                    (тем.group(1).decode(errors="replace")[:48]
                                     if тем else "?")))
            if нет:
                print("   %-34s %-10s писем %3d, без события %2d"
                      % (ящик[:34], папка[:10], len(uids), нет))
        except Exception as ex:                                   # noqa: BLE001
            print("   %-34s %-10s ошибка: %s" % (ящик[:34], папка[:10], str(ex)[:44]))
    try:
        im.logout()
    except Exception:                                             # noqa: BLE001
        pass
print("")
print("=== ИТОГ ===")
for к, n in итог.most_common():
    print("   %-16s %5d" % (к, n))
print("")
print("=== письма без события ===")
for я, п, u, от, тем in пропало[:40]:
    print("   %-30s %-8s uid %-5s %-40s %s" % (я[:30], п[:8], u, от, тем))
