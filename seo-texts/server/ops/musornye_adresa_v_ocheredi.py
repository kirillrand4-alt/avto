# -*- coding: utf-8 -*-
"""Две проверки по следам сегодняшних отбивок.

1. Осели ли приговоры трёх сегодняшних жёстких отбивок во всех базах -
   разбор входящих обязан писать их сам (правило CLAUDE.md о трёх базах).
2. Сколько в очереди ЗАВЕДОМО МУСОРНЫХ адресов вроде test@mail.ru: одна из
   трёх сегодняшних отбивок пришла именно на такой. Домен у него живой, MX
   есть, лёгкая проверка молчит - ловится только глазами или отбивкой,
   то есть ценой репутации.
"""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

АДРЕСА = ["a.nosov@iat38.ru", "shop@zavodsota.ru", "test@mail.ru"]
# Мусор - это не «роль» (info@, sales@ вполне рабочие), а явные заглушки.
# ПЕРВАЯ РЕДАКЦИЯ ЛОВИЛА ЛИШНЕЕ: в списке стояло «mail@», и под мусор попали
# три десятка рабочих корпоративных адресов - mail@zavodsm18.ru,
# mail@bzvs.ru и подобные. В России mail@домен это штатный ящик компании, а
# не заглушка. Оставляем только явные пустышки и плейсхолдеры.
МУСОР = re.compile(
    r'(?i)^(test|tests|testing|test\d+|example|sample|demo|temp|tmp|'
    r'noreply|no-reply|donotreply|nobody|qwerty|asdf|xxx|zzz|aaa|'
    r'firstname|lastname|yourname|123|1234|12345)@')

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("== приговоры сегодняшних отбивок ==")
for a in АДРЕСА:
    with store._lock:
        p = store._conn.execute(
            "SELECT verdict, source FROM addr_probe WHERE email=?",
            (a,)).fetchone()
        s_ = store._conn.execute(
            "SELECT reason FROM suppression WHERE value=?", (a,)).fetchone()
    e = o = None
    try:
        con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True,
                              timeout=10)
        r = con.execute("SELECT probe_verdict FROM emails WHERE email=?",
                        (a,)).fetchone()
        e = r[0] if r else None
        con.close()
    except Exception as ex:                                      # noqa: BLE001
        e = f"?{str(ex)[:40]}"
    try:
        con = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro",
                              uri=True, timeout=10)
        r = con.execute("SELECT verdict FROM email_probe WHERE email=?",
                        (a,)).fetchone()
        o = r[0] if r else None
        con.close()
    except Exception as ex:                                      # noqa: BLE001
        o = f"?{str(ex)[:40]}"
    print(f"  {a}")
    print(f"    addr_probe: {p[0] if p else 'НЕТ'} (источник {p[1] if p else '-'})"
          f" | enrich: {e or 'НЕТ'} | обзвон: {o or 'НЕТ'} "
          f"| стоп-лист: {'да' if s_ else 'НЕТ'}")

print("\n== мусорные адреса ==")
with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, lower(COALESCE(c.email,'')),
                  COALESCE(rc.company_name,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
            WHERE c.campaign_id IN (10,11)""").fetchall()
    все_получатели = store._conn.execute(
        "SELECT lower(COALESCE(email,'')) FROM recipients").fetchall()
счёт = Counter()
нашлись = []
for rid, st, email, имя in ряды:
    if МУСОР.match(email or ""):
        счёт[st] += 1
        нашлись.append((rid, st, email, имя))
в_базе = sum(1 for (e,) in все_получатели if МУСОР.match(e or ""))
print(f"в базе получателей всего: {в_базе}")
print(f"в очереди кампаний 10-11: {sum(счёт.values())} — {dict(счёт)}")
for rid, st, email, имя in нашлись[:20]:
    print(f"  #{rid:<6} {st:<9} {email:<34} {имя[:34]}")
