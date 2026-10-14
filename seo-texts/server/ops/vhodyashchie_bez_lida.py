# -*- coding: utf-8 -*-
"""Письма в ящиках, которые не дошли до панели лидов (владелец 13.10, после
«Герр Штрудель» и письма на a.tyunin).

1) События «входящее вне переписки» за N дней без лида — от живых людей.
2) Сверка ящиков по Message-ID с событиями (INBOX + спам) за те же дни:
   письмо, которого панель вообще не видела.
Только чтение.

    vhodyashchie_bez_lida.py [dney=14] [--bez-imap]
"""
import email.header
import imaplib
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
им = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ДНЕЙ = int(им.get("dney", "14"))
с_даты = time.strftime("%Y-%m-%d", time.localtime(time.time() - ДНЕЙ * 86400))
МАШИНА = re.compile(r"no-?reply|mailer-daemon|postmaster|notif|robot|bounce|support@|newsletter|rassylka|"
                    r"news@|info@(?:hh|mail|yandex|tinkoff|sber)|@(?:hh\.ru|yandex\.ru>?$|.*\.yandex\.net)|"
                    r"calendar|digest|subscribe|unsubscribe|daemon|@mail\.ru>?$\s*$", re.I)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
с_лидом = set()
for р in c.execute("SELECT source_event_id, dedup_key FROM leads"):
    if р["source_event_id"]:
        с_лидом.add(int(р["source_event_id"]))
    м = re.search(r":(\d+)$", str(р["dedup_key"] or ""))
    if м:
        с_лидом.add(int(м.group(1)))
print("== 1) «вне переписки» с %s без лида ==" % с_даты)
св = Counter()
for р in c.execute("SELECT id, event_ts, mailbox_id, detail_json FROM events WHERE event_type='other' "
                   "AND event_ts >= ? ORDER BY id", (с_даты,)):
    д = json.loads(р["detail_json"] or "{}")
    h = д.get("headers") or {}
    от = str(h.get("From") or д.get("from") or "")
    тема = str(h.get("Subject") or "")
    try:
        тема = str(email.header.make_header(email.header.decode_header(тема)))
        от = str(email.header.make_header(email.header.decode_header(от)))
    except Exception:  # noqa: BLE001
        pass
    if р["id"] in с_лидом:
        св["есть лид"] += 1
        continue
    if МАШИНА.search(от) or re.search(r"(?i)auto|автоответ|out of office|отпуск|недоставл|delivery|уведомлен", тема):
        св["машина/автоответ"] += 1
        if "--vse" in sys.argv and "id.yandex" not in от:   # фильтр ловит и людей с mail.ru/yandex.ru — показать глазами
            print("  [маш] #%d %s | от %s | %s | %s" % (р["id"], str(р["event_ts"])[:16], от[:45], тема[:40],
                  re.sub(r"\s+", " ", str(д.get("snippet") or ""))[:110]))
        continue
    св["ЧЕЛОВЕК БЕЗ ЛИДА"] += 1
    print("#%d %s %s | от %s | %s | %s" % (р["id"], str(р["event_ts"])[:16], р["mailbox_id"], от[:45], тема[:40],
          re.sub(r"\s+", " ", str(д.get("snippet") or ""))[:150]))
print("свод: %s" % dict(св))
if "--bez-imap" in sys.argv:
    print("=== ВХОДЯЩИЕ БЕЗ ЛИДА ===")
    sys.exit(0)
print("== 2) письма в ящиках без события (с %s) ==" % с_даты)
известные = {str(р[0]).strip() for р in c.execute("SELECT rfc_msgid FROM events WHERE rfc_msgid IS NOT NULL AND event_ts >= ?",
                                                  (time.strftime("%Y-%m-%d", time.localtime(time.time() - (ДНЕЙ + 3) * 86400)),))}
cfg = Config.load(r"C:\sender\sender.yaml")
ПАПКИ = ["INBOX", "Spam", "Junk", "INBOX.Spam", "&BCEEPwQwBDw-"]
SINCE = time.strftime("%d-%b-%Y", time.localtime(time.time() - ДНЕЙ * 86400))
итог = Counter()
for mb in cfg.mailboxes():
    пароль = os.getenv(mb.password_env, "")
    if not пароль:
        итог["ящик без пароля"] += 1
        continue
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
        im.login(mb.login, пароль)
    except Exception as ex:  # noqa: BLE001
        print("%s: вход не вышел: %s" % (mb.mailbox_id, str(ex)[:60]))
        continue
    доступные = []
    for стр in (im.list()[1] or []):
        м = re.search(rb'"([^"]+)"$', стр if isinstance(стр, bytes) else b"")
        if м:
            доступные.append(м.group(1).decode())
    for папка in ПАПКИ:
        if папка != "INBOX" and папка not in доступные:
            continue
        try:
            if im.select(папка, readonly=True)[0] != "OK":
                continue
            uids = (im.uid("SEARCH", None, "SINCE", SINCE)[1][0] or b"").split()
            if not uids:
                continue
            typ, md = im.uid("FETCH", b",".join(uids), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
            for ч in md or []:
                if not (isinstance(ч, tuple) and ч[1]):
                    continue
                сыр = ч[1]
                итог["писем"] += 1
                мид = re.search(rb"(?i)message-id:\s*(<[^>]+>)", сыр)
                мид = мид.group(1).decode(errors="replace").strip() if мид else ""
                if мид and (мид in известные or мид.strip("<>") in известные):
                    итог["есть событие"] += 1
                    continue
                if мид and c.execute("SELECT 1 FROM events WHERE detail_json LIKE ? LIMIT 1", ("%" + мид + "%",)).fetchone():
                    итог["есть событие"] += 1
                    continue
                от = re.search(rb"(?im)^from:\s*(.+)$", сыр)
                тем = re.search(rb"(?im)^subject:\s*(.+)$", сыр)
                дата = re.search(rb"(?im)^date:\s*(.+)$", сыр)
                def дек(x):
                    try:
                        return str(email.header.make_header(email.header.decode_header(x.group(1).decode(errors="replace").strip())))
                    except Exception:  # noqa: BLE001
                        return x.group(1).decode(errors="replace") if x else "?"
                о = дек(от) if от else "?"
                if МАШИНА.search(о):
                    итог["без события: машина"] += 1
                    continue
                итог["БЕЗ СОБЫТИЯ: человек"] += 1
                print("  %s %s | %s | от %s | %s" % (mb.mailbox_id, папка[:8], (дек(дата) if дата else "?")[:22], о[:45],
                                                    (дек(тем) if тем else "?")[:50]))
        except Exception as ex:  # noqa: BLE001
            print("  %s %s: ошибка %s" % (mb.mailbox_id, папка, str(ex)[:60]))
    try:
        im.logout()
    except Exception:  # noqa: BLE001
        pass
print("свод ящиков: %s" % dict(итог))
print("=== ВХОДЯЩИЕ БЕЗ ЛИДА ===")
