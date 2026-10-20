# -*- coding: utf-8 -*-
"""Второе касание Meyer — в «Подтвердить отправку» (владелец 20.10: «(а) только
257 адресов на доменах компаний — вот этих»).

Берёт _ops/meyer-vtoroe-kasanie.json (meyer_vtoroe_kasanie_spisok.py), только
адреса на домене компании (не публичные почтовики). Выбрасывает письма-
уточнения профиля («Уточнение по профилю», «ведёте ли вы сейчас…») — их
копировать незачем. Для каждого: получатель с карточкой прошлого адресата
(без имени контакта), сообщение в кампании 13 «Второе касание — Meyer», текст
и тема — копия последнего письма Meyer (обращение уже без имени), карточка
через ConfirmSend.submit (стоп-лист, мёртвый адрес, ответы, повтор — штатно).
Ящик-подсказка — тот, что писал первое письмо. Журнал — _ops/meyer-vk-ochered.jsonl.

    meyer_vtoroe_kasanie_v_ochered.py [--klast]"""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota         # noqa: E402
from sender.config import Config                   # noqa: E402
from sender.confirm import ConfirmSend             # noqa: E402
from sender.store import Store                     # noqa: E402
from sender.suppression import Suppression         # noqa: E402

КАМП = 13
ЖУР = r"C:\sender\_ops\meyer-vk-ochered.jsonl"
ПУБЛИЧНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru", "yandex.com"}
УТОЧНЕНИЕ = re.compile(r"(?i)уточнение по профилю|ведёте ли вы сейчас|в открытых источниках вижу|деятельность полн")
КЛАСТЬ = "--klast" in sys.argv

д = json.load(io.open(r"C:\sender\_ops\meyer-vtoroe-kasanie.json", encoding="utf-8"))
сч = Counter()
отбор = []
for x in д:
    if x["кому"].split("@")[-1] in ПУБЛИЧНЫЕ:
        сч["публичный почтовик (не берём)"] += 1
        continue
    if УТОЧНЕНИЕ.search((x.get("тема") or "") + " " + (x.get("тело") or "")):
        сч["письмо-уточнение профиля (не копируем)"] += 1
        continue
    отбор.append(x)
print("в списке:", len(д), "| к постановке:", len(отбор), dict(сч))
сделано = set()
if os.path.exists(ЖУР):
    сделано = {json.loads(s).get("кому") for s in io.open(ЖУР, encoding="utf-8")}
if not КЛАСТЬ:
    for x in отбор[:3]:
        print("\n-> %s (было %s, ящик %s)\nТема: %s\n%s" % (x["кому"], x["был_адрес"], x["исх_ящик"], x["тема"], x["тело"][:300]))
    print("\nСУХОЙ ПРОГОН. Класть — --klast")
    sys.exit()

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
итог = Counter()
ж = io.open(ЖУР, "a", encoding="utf-8")
for x in отбор:
    адр = x["кому"]
    if адр in сделано:
        итог["уже ставили"] += 1
        continue
    р = c.execute("SELECT * FROM recipients WHERE lower(email)=?", (x["был_адрес"],)).fetchone()
    есть = c.execute("SELECT id FROM recipients WHERE lower(email)=?", (адр,)).fetchone()
    if есть:
        rid = есть[0]
    else:
        теперь = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        ex = json.loads((р["extra_json"] if р else None) or "{}")
        ex.update({"vtoroe_kasanie_s": x["был_адрес"], "rol_vtorogo": x["роль"]})
        with c:
            cur = c.execute("INSERT INTO recipients (inn,email,domain,company_name,okved,segment,contact_name,source,region,"
                            "extra_json,tz,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (x["inn"], адр, адр.split("@")[-1], р["company_name"] if р else None, р["okved"] if р else None,
                             (р["segment"] if р else None) or "meyer", None, "vtoroe-kasanie-2010",
                             р["region"] if р else None, json.dumps(ex, ensure_ascii=False),
                             (р["tz"] if р else None) or "Europe/Moscow", теперь, теперь))
            rid = cur.lastrowid
    mid, _шаг, почему = q._ensure_message(КАМП, int(rid))
    if not mid:
        итог["сообщение не завелось: " + str(почему)[:40]] += 1
        continue
    тело = x["тело"].rstrip() + "\n\nС уважением,"
    r = cs.submit(email=адр, subject=x["тема"], body=тело, inn=x["inn"], campaign_id=КАМП, recipient_id=rid,
                  message_id=mid, panel={"letter_division": "meyer", "kopiya_s": x["был_адрес"],
                                         "mailbox_id": x["исх_ящик"], "vtoroe_kasanie": True})
    итог["очередь: " + str(r.status) + ((" " + str(r.reason)[:40]) if getattr(r, "reason", None) else "")] += 1
    ж.write(json.dumps({"кому": адр, "inn": x["inn"], "review": r.review_id, "status": r.status}, ensure_ascii=False) + "\n")
    ж.flush()
    os.fsync(ж.fileno())
print("ИТОГ:", dict(итог.most_common()))
