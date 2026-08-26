# -*- coding: utf-8 -*-
"""Спам-тест: с КАЖДОГО ящика по одному настоящему письму на адрес владельца.

Владелец 26.08: письмо с optic-sort.ru упало у Gmail в спам; отклик по
доменам расходится вчетверо (0.8% против 3.5%) при одинаковых SPF/DKIM/
DMARC. Прямой тест: пусть каждый ящик отправит РЕАЛЬНО ОТПРАВЛЕННОЕ им
письмо на один и тот же адрес, и станет видно, чьи письма фильтр кладёт в
спам.

Письмо берём из messages.body_rendered — ровно то, что ушло получателю.
Тему и текст не трогаем: спам-фильтр судит и по ним, подменять их значит
испортить тест. Отправитель узнаётся по адресу From.

Это РУЧНАЯ отправка на адрес владельца по его прямой просьбе: ни прогрев,
ни рассылка холдом не затронуты.

    python spam_test_vse_yashchiki.py                 # показать план
    python spam_test_vse_yashchiki.py primenit        # отправить
    python spam_test_vse_yashchiki.py komu=адрес
"""
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime, formataddr
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")
from sender.config import Config                             # noqa: E402
from sender.gates import Gates                               # noqa: E402
from sender.sender import Sender                             # noqa: E402
from sender.store import Store                               # noqa: E402
from sender.suppression import Suppression                   # noqa: E402

_имен = {}
for _а in list(sys.argv[1:]):
    if "=" in _а:
        к, з = _а.split("=", 1)
        _имен[к.strip()] = з.strip()
ДЕЛАТЬ = "primenit" in sys.argv[1:]
КОМУ = _имен.get("komu") or "martiushov@prokompressor.ru"
ПАУЗА = float(_имен.get("pauza") or 4.0)

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(БАЗА)
c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

план = []
for mb in cfg.mailboxes():
    п = c.execute(
        "SELECT m.id, m.sent_at, m.subject, m.body_rendered body, r.company_name "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.mailbox_id=? AND m.sent_at IS NOT NULL "
        "   AND COALESCE(m.body_rendered,'') <> '' "
        "   AND m.body_rendered NOT LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%' "
        " ORDER BY m.sent_at DESC LIMIT 1", (mb.mailbox_id,)).fetchone()
    if п is None:
        print("%-42s нет отправленных писем с телом — пропуск" % mb.mailbox_id[:42])
        continue
    план.append((mb, п))

print("")
print("кому: %s" % КОМУ)
print("писем к отправке: %d (по одному с каждого ящика)" % len(план))
домены = {}
for mb, _п in план:
    домены[mb.mailbox_id.rsplit("@", 1)[-1]] = домены.get(
        mb.mailbox_id.rsplit("@", 1)[-1], 0) + 1
print("доменов: %d — %s" % (len(домены), ", ".join(sorted(домены))))
for mb, п in план:
    print("   %-42s %-30s %s" % (mb.mailbox_id[:42], (mb.from_name or "")[:30],
                                 str(п["subject"])[:52]))

if not ДЕЛАТЬ:
    print("\nвхолостую. Отправить — primenit")
    raise SystemExit(0)

s = Sender(cfg, store, Suppression(store), Gates(cfg, store))
ушло = сбоев = 0
for mb, п in план:
    rfc = s._gen_message_id(mb.mailbox_id)
    заголовки = {
        "Message-ID": rfc,
        "Date": format_datetime(datetime.now(timezone.utc)),
        "From": formataddr((mb.from_name, mb.mailbox_id)),
        "To": КОМУ,
        "Subject": str(п["subject"]),
        "MIME-Version": "1.0",
    }
    mime = s._build_mime(заголовки, SimpleNamespace(
        body=str(п["body"]), subject=str(п["subject"]), unfilled_fields=[]))
    try:
        s._deliver(mb, mb.mailbox_id, КОМУ, mime)
        ушло += 1
        print("ушло  %-42s %s" % (mb.mailbox_id[:42], rfc))
    except Exception as ex:                                   # noqa: BLE001
        сбоев += 1
        print("СБОЙ  %-42s %s" % (mb.mailbox_id[:42], str(ex)[:90]))
    time.sleep(ПАУЗА)
c.close()
print("")
print("итог: ушло %d, сбоев %d" % (ушло, сбоев))
