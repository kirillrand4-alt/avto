# -*- coding: utf-8 -*-
"""Привязать событие 293944 к получателю и завести карточку лида.

Автоответ «я закончила работу в компании, обращайтесь к Пушиной Александре
Вячеславовне <pav4@virtex-food.ru>» — это не мусор, а смена контакта: адрес
преемника надо сохранить, иначе он потеряется вместе с событием.
"""
import json
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
СОБЫТИЕ = 293944
ПОЛУЧАТЕЛЬ = 30282          # sales-p@virtex-food.ru, ООО «ВТ ЛОГИСТИК»
ПРЕЕМНИК = "pav4@virtex-food.ru"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
e = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
r = c.execute("SELECT id, email, inn, company_name FROM recipients WHERE id=?",
              (ПОЛУЧАТЕЛЬ,)).fetchone()
есть_лид = c.execute("SELECT id, status FROM leads WHERE recipient_id=?",
                     (ПОЛУЧАТЕЛЬ,)).fetchone()
c.close()
print("событие: %s  привязка сейчас: %s" % (e["id"], e["recipient_id"]))
print("получатель: %s | %s | ИНН %s" % (r["email"], r["company_name"], r["inn"]))
print("лид по нему: %s" % (dict(есть_лид) if есть_лид else "нет"))
d = json.loads(e["detail_json"] or "{}")
print("текст: %s" % str(d.get("snippet"))[:150])
if not КАТИТЬ:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store.transaction() as conn:
    n = conn.execute("UPDATE events SET recipient_id=? WHERE id=? "
                     "  AND recipient_id IS NULL", (ПОЛУЧАТЕЛЬ, СОБЫТИЕ)).rowcount
print("событие привязано: %d" % n)

десk = LeadDesk(cfg, store)
ок = десk.push_warm_lead(
    r["email"], None,
    "[redirect] %s" % str(d.get("snippet") or "")[:400],
    otvetil="dmg@virtex-food.ru")
print("карточка лида: %s" % ("создана" if ок else "уже была"))

# адрес преемника — в обогащение, чтобы не потерялся
# enrich.db жуёт обогащение параллельно — ждём и повторяем, а не падаем
o = None
for попытка in range(5):
    try:
        o = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
        o.execute("PRAGMA busy_timeout=120000")
        o.execute("SELECT 1 FROM emails LIMIT 1").fetchone()
        break
    except sqlite3.OperationalError as ex:
        print("   enrich занят (%s), повтор %d" % (str(ex)[:40], попытка + 1))
        time.sleep(4 * (попытка + 1))
        o = None
if o is None:
    print("enrich.db не открылся — преемник не записан, повторить позже")
    raise SystemExit(0)
уже = o.execute("SELECT 1 FROM emails WHERE email=? LIMIT 1", (ПРЕЕМНИК,)).fetchone()
if not уже:
    for попытка in range(5):
        try:
            o.execute("INSERT INTO emails (inn, email, role, person, source, updated_at) "
              " VALUES (?,?,?,?,?,?)",
                      (r["inn"], ПРЕЕМНИК, "свой",
                       "Пушина Александра Вячеславовна",
                       "автоответ о смене контакта",
                       time.strftime("%Y-%m-%dT%H:%M:%S")))
            o.commit()
            print("преемник %s добавлен в обогащение" % ПРЕЕМНИК)
            break
        except sqlite3.OperationalError as ex:
            print("   занято (%s), повтор %d" % (str(ex)[:40], попытка + 1))
            time.sleep(4 * (попытка + 1))
else:
    print("преемник %s уже был в обогащении" % ПРЕЕМНИК)
o.close()
