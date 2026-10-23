# -*- coding: utf-8 -*-
"""Повторная SMTP-проба адресов с вердиктом «неясно» (владелец 23.10: «пробу
неясно ещё раз прогони») — запасные адреса лесенки кампании <id>: компании,
которым кампания писала и которые не ответили; адрес ещё не писан, роль годна.
probe(force=True) — мимо кэша; темп: 3 с между пробами, крупные публичные
домены — раз в 20 с на домен. Вердикт — во все три базы (addr_probe пишет сама
проба; enrich.emails и obzvon-index.email_probe — здесь), журнал с fsync.
    reproba_neyasno.py <campaign_id> --zapusk | <campaign_id> (ход)"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

cid = int(sys.argv[1])
ХОД = r"C:\sender\_ops\reproba-neyasno-%d.json" % cid
ЖУРНАЛ = r"C:\sender\_ops\reproba-neyasno-%d.jsonl" % cid
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.by",
           "yandex.com", "narod.ru", "gmail.com", "rambler.ru", "tut.by", "mail.by"}
if "--zapusk" in sys.argv:
    л = io.open(r"C:\sender\_ops\reproba-neyasno-%d.log" % cid, "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), str(cid), "--rabota"], cwd=r"C:\sender",
                         stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(20)
    print("повторная проба запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    try:
        print(io.open(ХОД, encoding="utf-8").read()[:400])
    except OSError:
        pass
    sys.exit(0)
if "--rabota" not in sys.argv:
    try:
        print(io.open(ХОД, encoding="utf-8").read())
    except OSError:
        print("хода нет")
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.addr_probe import build_addr_probe  # noqa: E402
from sender.config import Config                # noqa: E402
from sender.store import Store                  # noqa: E402
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|финанс|hr|резюме|не для письма")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
проба_в = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
писали = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log WHERE outcome='sent'")}
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
ответ |= {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id "
                                       "WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
инн = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                    "WHERE m.campaign_id=? AND m.status='sent' AND r.inn IS NOT NULL", (cid,))} - ответ
очередь = []
for i in sorted(инн):
    for а, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (i,)):
        роль = str(роль or "")
        if а and проба_в.get(а) == "неясно" and а not in писали and not ПЛОХО.search(роль + " " + а.split("@")[0]) \
                and _rol_ball(роль) > 1:
            очередь.append((а, i))
c.close()
e.close()
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
петля = build_addr_probe(store, cfg)
проба = getattr(петля, "probe", None) or getattr(петля, "probe_")
проба.per_domain = 10 ** 6
ход = {"старт": time.strftime("%H:%M:%S"), "всего": len(очередь), "проверено": 0, "вердикты": {}}


def отметить():
    with io.open(ХОД, "w", encoding="utf-8") as ф:
        json.dump(ход, ф, ensure_ascii=False)
        ф.flush()
        os.fsync(ф.fileno())


def в_базы(адрес, инн_, вер, ответ_):
    ts = int(time.time())
    for путь, sql, пар in (
            (r"C:\sender\enrich.db", "UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?",
             (вер, ts, str(ответ_)[:300], адрес)),
            (r"C:\sender\obzvon-index.db", "INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) "
             "ON CONFLICT(email) DO UPDATE SET verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts",
             (адрес, вер, "smtp-reproba", str(ответ_)[:300], ts))):
        try:
            x = sqlite3.connect(путь, timeout=60)
            x.execute(sql, пар)
            x.commit()
            x.close()
        except Exception:  # noqa: BLE001
            pass
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": ts, "email": адрес, "inn": инн_, "verdict": вер}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())


отметить()
посл = {}
while очередь:
    отложено = []
    for адрес, инн_ in очередь:
        дом = адрес.rsplit("@", 1)[-1]
        if дом in КРУПНЫЕ and time.monotonic() - посл.get(дом, -1e9) < 20:
            отложено.append((адрес, инн_))
            continue
        посл[дом] = time.monotonic()
        try:
            рез = проба.probe(адрес, force=True)
        except Exception as ex:  # noqa: BLE001
            рез = {"verdict": "неясно", "answer": str(ex)[:200]}
        вер = str(рез.get("verdict") or "неясно")
        ход["проверено"] += 1
        ход["вердикты"][вер] = ход["вердикты"].get(вер, 0) + 1
        в_базы(адрес, инн_, вер, рез.get("answer") or "")
        if ход["проверено"] % 10 == 0:
            отметить()
        time.sleep(3)
    очередь = отложено
    if очередь:
        time.sleep(5)
ход["финиш"] = time.strftime("%H:%M:%S")
отметить()
