# -*- coding: utf-8 -*-
"""Привязать три потерянных ответа и завести карточки лидов.

Все три пришли с публичных почтовиков: клиент переслал наше письмо коллеге
или ответил с личного ящика. Домен там ничего не значит, адрес в базе не
числился — привязки не было, и ответы месяц лежали событиями «other».
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПАРЫ = [
    (183709, 17636, "s9213674759@gmail.com", "otkaz",
     "Сергей Голышев: вопрос с компрессорами не актуален, мы их продаём. "
     "Если есть интерес по выкупу, то пишите."),
    (182154, 15310, "sever-snab74@mail.ru", "otkaz",
     "Про Тепло, отдел снабжения: у нас стоят винтовые компрессоры Comprag, "
     "пока всё устраивает. тел 8 909 077 09 03 Андрей, 8 (351) 215-11-44"),
    (59167, 4044, "olegraufa@mail.ru", "otkaz",
     "Гузель Олейник (переслано из клиники): для нас не актуально, "
     "благодарю за предложение."),
]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for eid, rid, откуда, вид, текст in ПАРЫ:
    e = c.execute("SELECT recipient_id, event_ts FROM events WHERE id=?",
                  (eid,)).fetchone()
    r = c.execute("SELECT email, company_name FROM recipients WHERE id=?",
                  (rid,)).fetchone()
    л = c.execute("SELECT id, status FROM leads WHERE recipient_id=?",
                  (rid,)).fetchone()
    print("#%-7s %s -> rid %s %-26s %s | привязка сейчас: %s | лид: %s"
          % (eid, откуда[:26], rid, str(r["email"])[:26],
             str(r["company_name"])[:26], e["recipient_id"], dict(л) if л else "нет"))
c.close()
if not КАТИТЬ:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
десk = LeadDesk(cfg, store)
for eid, rid, откуда, вид, текст in ПАРЫ:
    with store.transaction() as conn:
        n = conn.execute("UPDATE events SET recipient_id=? WHERE id=? "
                         "  AND recipient_id IS NULL", (rid, eid)).rowcount
    r = store.get_recipient(rid)
    ок = None
    try:
        ок = десk.push_warm_lead(getattr(r, "email", ""), None,
                                 "[%s] %s" % (вид, текст), otvetil=откуда)
    except Exception as ex:                                      # noqa: BLE001
        ок = "ошибка: %s" % str(ex)[:70]
    print("#%s привязано=%d, лид=%s" % (eid, n, ок))
