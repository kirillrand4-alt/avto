# -*- coding: utf-8 -*-
"""Входящие без лида: ответы и «вне переписки» за N дней, к которым в leads нет
ни лида по событию, ни по получателю, ни по адресу отправителя, ни по ИНН.
Только чтение.  lidy_nezavedennye.py [дней=14] [типы=reply,other]"""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter

import requests

ВЫХ = []
_print = print


def print(*a):  # noqa: A001 — всё и в файл на дроп (раннер режет хвост)
    ВЫХ.append(" ".join(str(x) for x in a))
    _print(*a)



N = int(sys.argv[1]) if len(sys.argv) > 1 else 14
ТИПЫ = tuple((sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "reply,other").split(","))   # напр. reply_auto
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
print("типы событий за %d дней:" % N, Counter(r[0] for r in c.execute(
    "SELECT event_type FROM events WHERE event_ts >= datetime('now', ?) AND event_type NOT IN ('sent','open')",
    ("-%d days" % N,))).most_common(20))
по_соб, по_пол, по_адр, по_инн = set(), set(), set(), set()
for r in c.execute("SELECT source_event_id, recipient_id, lower(email), inn FROM leads"):
    по_соб.add(r[0]); по_пол.add(r[1]); по_адр.add(r[2]); по_инн.add(str(r[3] or ""))
инн_пол = {r[0]: str(r[1] or "") for r in c.execute("SELECT id, inn FROM recipients")}
n = 0
for е in c.execute("SELECT * FROM events WHERE event_ts >= datetime('now', ?) AND event_type IN (%s) "
                   "ORDER BY id DESC" % ",".join("?" * len(ТИПЫ)), ("-%d days" % N,) + ТИПЫ):
    d = json.loads(е["detail_json"] or "{}")
    h = d.get("headers") or {}
    адр = (re.findall(r"[\w.+-]+@[\w.-]+", str(h.get("From") or "")) or [""])[0].lower()
    инн = инн_пол.get(е["recipient_id"], "")
    if "--vse" not in sys.argv and (е["id"] in по_соб or (е["recipient_id"] and е["recipient_id"] in по_пол) or адр in по_адр or (инн and инн in по_инн)):
        continue
    n += 1
    сн = re.sub(r"\s+", " ", str(d.get("snippet") or ""))[:600]
    print("\n#%s %s %s | ящик %s | rid %s инн %s\n  от: %s\n  тема: %s\n  %s" % (
        е["id"], е["event_type"], е["event_ts"][:16], е["mailbox_id"], е["recipient_id"], инн,
        str(h.get("From") or "")[:90], str(h.get("Subject") or "")[:100], сн))
print("\nвсего без лида:", n)
т = "\n".join(ВЫХ) + "\n"
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/lidy-nezavedennye-%s.txt" % "-".join(ТИПЫ),
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
