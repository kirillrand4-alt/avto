# -*- coding: utf-8 -*-
"""Тестовая отправка владельцу КОПИЙ настоящих писем с двух ящиков:
одного нового домена и одного прогретого.

Сделано по прямой просьбе владельца. Берём последнее реально отправленное
письмо каждого ящика (messages.body_rendered) и шлём его как есть: тему,
текст и заголовки не подменяем, иначе тест не про спам-фильтр. Письма с
неподставленной меткой ИМЯ_ОТПРАВИТЕЛЯ пропускаем.

Идёт мимо пауз и рампы намеренно: это ручная отправка на свой адрес, а не
рассылка. На счётчики и статистику не влияет - событий sent не пишем.

    test_dva_yashchika_0901.py                      показать план
    test_dva_yashchika_0901.py primenit             отправить
    test_dva_yashchika_0901.py komu=адрес novyy=... staryy=...
"""
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime, formataddr
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.gates import Gates            # noqa: E402
from sender.sender import Sender          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402

_им = {}
for _а in list(sys.argv[1:]):
    if "=" in _а:
        к, з = _а.split("=", 1)
        _им[к.strip()] = з.strip()
ДЕЛАТЬ = "primenit" in sys.argv[1:]
КОМУ = _им.get("komu") or "kirillrand4@gmail.com"
НОВЫЙ = _им.get("novyy") or "d.ivanov@sorting-systems.ru"
СТАРЫЙ = _им.get("staryy") or "a.miroshnichenko@optic-sort.ru"

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(БАЗА)
c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

ящики = {mb.mailbox_id: mb for mb in cfg.mailboxes()}
план = []
for метка, mid in (("НОВЫЙ домен", НОВЫЙ), ("ПРОГРЕТЫЙ домен", СТАРЫЙ)):
    mb = ящики.get(mid)
    if mb is None:
        print("%-16s %s — нет такого ящика в конфиге" % (метка, mid))
        continue
    п = c.execute(
        "SELECT m.id, m.sent_at, m.subject, m.body_rendered body, r.company_name"
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.mailbox_id=? AND m.sent_at IS NOT NULL"
        "   AND COALESCE(m.body_rendered,'') <> ''"
        "   AND m.body_rendered NOT LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'"
        " ORDER BY m.sent_at DESC LIMIT 1", (mid,)).fetchone()
    if п is None:
        print("%-16s %s — нет отправленных писем с телом" % (метка, mid))
        continue
    план.append((метка, mb, п))

print("\n=== ПЛАН ===")
print("  кому: %s" % КОМУ)
for метка, mb, п in план:
    print("  %-16s %-38s" % (метка, mb.mailbox_id[:38]))
    print("     от кого : %s" % (mb.from_name or ""))
    print("     тема    : %s" % str(п["subject"])[:70])
    print("     ушло    : %s компании %s"
          % (str(п["sent_at"])[:19], str(п["company_name"])[:30]))
    print("     длина   : %d знаков" % len(str(п["body"] or "")))

if not ДЕЛАТЬ:
    print("\n=== ИТОГ ===")
    print("  вхолостую, ничего не отправлено. Отправить — аргумент primenit")
    raise SystemExit(0)

s = Sender(cfg, store, Suppression(store), Gates(cfg, store))
ушло = сбоев = 0
for метка, mb, п in план:
    rfc = s._gen_message_id(mb.mailbox_id)
    заг = {"Message-ID": rfc,
           "Date": format_datetime(datetime.now(timezone.utc)),
           "From": formataddr((mb.from_name, mb.mailbox_id)),
           "To": КОМУ,
           "Subject": str(п["subject"]),
           "MIME-Version": "1.0"}
    mime = s._build_mime(заг, SimpleNamespace(
        body=str(п["body"]), subject=str(п["subject"]), unfilled_fields=[]))
    try:
        s._deliver(mb, mb.mailbox_id, КОМУ, mime)
        ушло += 1
        print("ушло  %-16s %-38s %s" % (метка, mb.mailbox_id[:38], rfc))
    except Exception as ex:  # noqa: BLE001
        сбоев += 1
        print("СБОЙ  %-16s %-38s %s" % (метка, mb.mailbox_id[:38], str(ex)[:90]))
    time.sleep(4.0)
c.close()
print("\n=== ИТОГ ===")
print("  ушло %d, сбоев %d, адрес %s" % (ушло, сбоев, КОМУ))
