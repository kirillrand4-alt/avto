# -*- coding: utf-8 -*-
"""Отправить владельцу НАСТОЯЩЕЕ письмо с мейеровского ящика — на спам-тест.

Владелец 26.08: у v.ivanov@optic-sort.ru 137 отправок и ноль ответов;
просил прислать письмо оттуда на его почту, чтобы посмотреть глазами и
увидеть, куда оно падает.

Берём РЕАЛЬНО ОТПРАВЛЕННОЕ письмо этого ящика и повторяем его слово в
слово, с теми же заголовками (From с именем, отписка, Message-ID) — иначе
тест ничего не покажет: спам-фильтр судит по конверту, а не по тексту.

Это РУЧНАЯ отправка ОДНОГО письма на адрес владельца по его прямой
просьбе. Ни прогрев, ни рассылка холдом не затронуты.

    python pismo_vladelcu.py                     # показать, что отправим
    python pismo_vladelcu.py primenit            # отправить
    python pismo_vladelcu.py komu=адрес          # другой адрес
"""
import sqlite3
import sys

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
ЯЩИК = _имен.get("yashchik") or "v.ivanov@optic-sort.ru"
КОМУ = _имен.get("komu") or "kirillrand4@gmail.com"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(cfg.get("service.db_path", r"C:\sender\sender.db"),
                    timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

# ТЕЛО БЕРЁМ ИЗ messages.body_rendered — это то, что РЕАЛЬНО ушло.
# В confirm_reviews лежит ШАБЛОН с меткой ИМЯ_ОТПРАВИТЕЛЯ: движок
# подставляет имя на отправке (gender_agree.подставить_имя), и письмо с
# меткой из карточки было бы не тестом, а подделкой теста.
письмо = c.execute(
    "SELECT m.id, m.sent_at, m.recipient_id, m.subject, "
    "       m.body_rendered body, r.company_name "
    "  FROM messages m LEFT JOIN recipients r ON r.id = m.recipient_id "
    " WHERE m.mailbox_id=? AND m.sent_at IS NOT NULL "
    "   AND COALESCE(m.body_rendered,'') <> '' "
    " ORDER BY m.sent_at DESC LIMIT 1", (ЯЩИК,)).fetchone()
if письмо is None:
    print("у ящика %s нет отправленных писем с телом" % ЯЩИК)
    raise SystemExit(1)

mb = next((x for x in cfg.mailboxes() if x.mailbox_id == ЯЩИК), None)
if mb is None:
    print("ящика %s нет в настройках" % ЯЩИК)
    raise SystemExit(1)

print("ящик:      %s (%s)" % (ЯЩИК, mb.from_name))
print("SMTP:      %s:%s" % (mb.smtp_host, mb.smtp_port))
print("кому:      %s" % КОМУ)
если_метка = "ИМЯ_ОТПРАВИТЕЛЯ" in str(письмо["body"] or "")
print("метка имени в теле: %s" % ("ЕСТЬ — это шаблон, не отправляем"
                                  if если_метка else "нет, имя подставлено"))
print("образец:   письмо #%s от %s, компания %s"
      % (письмо["id"], str(письмо["sent_at"])[:19], письмо["company_name"]))
print("тема:      %s" % письмо["subject"])
print("")
print(str(письмо["body"])[:1200])

if если_метка:
    print("\nв теле осталась метка — отправлять нельзя, это шаблон")
    raise SystemExit(1)
if not ДЕЛАТЬ:
    print("\nвхолостую. Отправить — primenit")
    raise SystemExit(0)

from email.utils import formataddr, format_datetime           # noqa: E402
from datetime import datetime, timezone                       # noqa: E402
from types import SimpleNamespace                             # noqa: E402

s = Sender(cfg, store, Suppression(store), Gates(cfg, store))
rfc = s._gen_message_id(ЯЩИК)
заголовки = {
    "Message-ID": rfc,
    "Date": format_datetime(datetime.now(timezone.utc)),
    "From": formataddr((mb.from_name, mb.mailbox_id)),
    "To": КОМУ,
    "Subject": str(письмо["subject"]),
    "MIME-Version": "1.0",
}
# Те же заголовки отписки, что у боевого письма: спам-фильтр смотрит и на них.
try:
    токен = s._make_unsub_token(int(письмо["recipient_id"] or 0), None)
    заголовки.update(s._list_unsubscribe_headers(токен, mb))
except Exception as ex:                                       # noqa: BLE001
    print("заголовки отписки не собрались: %s" % str(ex)[:80])

mime = s._build_mime(заголовки,
                     SimpleNamespace(body=str(письмо["body"]),
                                     subject=str(письмо["subject"]),
                                     unfilled_fields=[]))
print("заголовки: %s" % ", ".join(sorted(заголовки)))
s._deliver(mb, mb.mailbox_id, КОМУ, mime)
print("\nотправлено: %s -> %s, Message-ID %s" % (ЯЩИК, КОМУ, rfc))
c.close()
