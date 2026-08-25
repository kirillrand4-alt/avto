# -*- coding: utf-8 -*-
"""Карточка ответу «ТЭКО»: письмо человеческое, но легло как «прочее».

Сергей Голышев ответил не в ветку, а НОВЫМ письмом с личного gmail и темой
«Ооо ТЭКО». Сторож не нашёл ни In-Reply-To, ни получателя — событие ушло в
«other», карточки не завелось. Ответ при этом деловой: «вопрос с
компрессорами не актуален, мы их продаём, если есть интерес по выкупу, то
пишите» — это поставщик, а не отказ впустую.

Компанию берём не с потолка: тема письма называет её, и часом раньше мы
писали ООО «ТЭКО» на teko2022@yandex.ru с того же ящика, куда пришёл ответ.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config      # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.store import Store        # noqa: E402

СОБЫТИЕ = 183709
БАЗА = r"C:\sender\sender.db"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

c = sqlite3.connect(БАЗА, timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
d = json.loads(р["detail_json"] or "{}")
з = d.get("headers") or {}
адрес = str(з.get("From") or "").split("<")[-1].strip("<> ").lower()
текст = " ".join(str(d.get("snippet") or "").split())
рек = c.execute("SELECT id, email, company_name, inn FROM recipients "
                " WHERE LOWER(email)='teko2022@yandex.ru'").fetchone()
print("событие: %s | ящик %s" % (р["event_ts"], р["mailbox_id"]))
print("от:      %s" % з.get("From"))
print("текст:   %s" % текст[:160])
print("компания: %s" % (dict(рек) if рек else "не нашлась"))
уже = c.execute("SELECT id FROM leads WHERE LOWER(email)=?", (адрес,)).fetchone()
print("карточка на этот адрес: %s" % (уже["id"] if уже else "нет"))
if not ДЕЛАТЬ:
    print("\nвхолостую. Завести — primenit")
    raise SystemExit(0)
if уже:
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
объект = store.get_recipient(int(рек["id"])) if рек else None
lid = LeadDesk(cfg, store).push_warm_lead(
    объект, "", "[not_interested] %s" % текст, otvetil=адрес)
print("заведена карточка: %s" % lid)
for х in sqlite3.connect(БАЗА).execute(
        "SELECT id, email, company_name, inn, reply_kind FROM leads WHERE id=?",
        (lid,)):
    print("   %s" % (х,))
