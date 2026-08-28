# -*- coding: utf-8 -*-
"""Дописать лиду 223 компанию и завести преемника в обогащение."""
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
r = store.get_recipient(30282)
with store.transaction() as conn:
    n = conn.execute(
        "UPDATE leads SET recipient_id=?, company_name=?, inn=?, updated_at=? "
        " WHERE id=223 AND recipient_id IS NULL",
        (30282, getattr(r, "company_name", None), getattr(r, "inn", None),
         time.strftime("%Y-%m-%dT%H:%M:%S"))).rowcount
print("лид 223 привязан к компании: %d (%s)" % (n, getattr(r, "company_name", "?")))

ПРЕЕМНИК = "pav4@virtex-food.ru"
готово = False
for попытка in range(40):
    try:
        o = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
        o.execute("PRAGMA busy_timeout=60000")
        есть = o.execute("SELECT 1 FROM emails WHERE email=? LIMIT 1",
                         (ПРЕЕМНИК,)).fetchone()
        if not есть:
            o.execute(
                "INSERT INTO emails (inn, email, role, person, source, updated_at) "
                " VALUES (?,?,?,?,?,?)",
                (getattr(r, "inn", None), ПРЕЕМНИК, "свой",
                 "Пушина Александра Вячеславовна",
                 "автоответ о смене контакта",
                 time.strftime("%Y-%m-%dT%H:%M:%S")))
            o.commit()
            print("преемник %s добавлен" % ПРЕЕМНИК)
        else:
            print("преемник %s уже был" % ПРЕЕМНИК)
        o.close()
        готово = True
        break
    except sqlite3.OperationalError as ex:
        print("   enrich занят (%s), повтор %d" % (str(ex)[:36], попытка + 1))
        time.sleep(15)
if not готово:
    print("enrich.db занят — преемник не записан, повторить позже")
