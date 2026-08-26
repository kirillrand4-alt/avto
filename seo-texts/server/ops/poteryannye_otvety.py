# -*- coding: utf-8 -*-
"""Все входящие без привязки к компании: сколько и что в них.

«Шато де Талю» показал дыру: ответ с другого ящика конторы без In-Reply-To
ложился событием без получателя и мимо ленты лидов. Смотрим, сколько таких.
"""
import json
import re
import sqlite3
from collections import Counter

ОБЩИЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru",
         "ya.ru", "yandex.com", "gmail.com", "googlemail.com", "rambler.ru",
         "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
         "mail.com", "protonmail.com", "proton.me", "narod.ru"}
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

ряды = c.execute(
    "SELECT id, event_type, event_ts, detail_json FROM events "
    " WHERE recipient_id IS NULL AND event_type IN "
    "       ('reply','reply_auto','other','complaint') ORDER BY event_ts"
).fetchall()
print("входящих без получателя: %d" % len(ряды))
виды = Counter(r["event_type"] for r in ряды)
print("по видам: %s" % dict(виды))


def отправитель(d):
    h = d.get("headers") or {}
    if isinstance(h, dict):
        for к in ("From", "from", "Return-Path", "Reply-To"):
            строка = str(h.get(к) or "")
            м = АДРЕС.search(строка)
            if м:
                return м.group(0).lower()
    for к in ("from", "from_addr", "otvetil", "sender"):
        м = АДРЕС.search(str(d.get(к) or ""))
        if м:
            return м.group(0).lower()
    return ""


свод = Counter()
привязались = []
for r in ряды:
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:                                         # noqa: BLE001
        d = {}
    а = отправитель(d)
    if not а:
        свод["адрес отправителя не нашёлся"] += 1
        continue
    дом = а.rsplit("@", 1)[-1]
    точный = c.execute("SELECT id, company_name FROM recipients WHERE email=?",
                       (а,)).fetchone()
    if точный:
        свод["привязался по адресу"] += 1
        привязались.append((r, d, а, точный, "адрес"))
        continue
    if дом in ОБЩИЕ:
        свод["публичный почтовик — не привязываем"] += 1
        continue
    свои = c.execute("SELECT id, inn, company_name FROM recipients "
                     " WHERE lower(domain)=? OR lower(email) LIKE ?",
                     (дом, "%@" + дом)).fetchall()
    инны = {str(x["inn"] or "") for x in свои}
    инны.discard("")
    if not свои:
        свод["домен не наш"] += 1
    elif len(инны) > 1:
        свод["на домене две компании"] += 1
    else:
        свод["привязался по домену"] += 1
        привязались.append((r, d, а, свои[0], "домен"))

print("")
print("=== разбор ===")
for имя, n in свод.most_common():
    print("   %-34s %d" % (имя, n))

print("")
print("=== что привязалось (%d) ===" % len(привязались))
for r, d, а, rec, как in привязались[:30]:
    т = " ".join(str(d.get("snippet") or "").split())[:95]
    print("   %s %-11s %-30s → %-34s [%s]"
          % (str(r["event_ts"])[:16], r["event_type"], а[:30],
             str(rec["company_name"])[:34], как))
    print("      %s" % т)
c.close()
