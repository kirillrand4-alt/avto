# -*- coding: utf-8 -*-
"""Только чтение: годятся ли исходные письма 639 компаний под копию."""
import datetime as dt
import re
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
граница = (utc - dt.timedelta(days=3)).isoformat()


def дом(u):
    u = str(u or "").strip().lower()
    if not u:
        return ""
    u = re.sub(r"^https?://", "", u).split("/")[0].split("?")[0]
    return u[4:] if u.startswith("www.") else u


# те же шаги отбора, что и в подсчёте
писали = {}
for р in s.execute("SELECT r.inn, MAX(m.sent_at) п FROM messages m JOIN recipients r"
                   " ON r.id=m.recipient_id WHERE m.status='sent' AND m.campaign_id<>12"
                   " AND r.inn IS NOT NULL AND r.inn<>'' GROUP BY r.inn"):
    if str(р["п"]) <= граница:
        писали[р["inn"]] = р["п"]
ответили = {р["inn"] for р in s.execute(
    "SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id"
    " WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
кандидаты = [i for i in писали if i not in ответили]
выр, див = {}, {}
for i in range(0, len(кандидаты), 800):
    к = кандидаты[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE inn IN (%s)" % q, к):
        выр[р["inn"]] = р["revenue_rub"]
    for р in o.execute("SELECT inn, division FROM obzvon WHERE inn IN (%s)" % q, к):
        див[р["inn"]] = р["division"] or ""
цель = [i for i in кандидаты
        if (выр.get(i) or 0) >= 30_000_000 and "meyer" in (див.get(i) or "")]
print("компаний после выручки и направления: %d" % len(цель))

ст = {"есть метка": 0, "имя вместо метки": 0, "нет текста": 0}
обращение = {"без имени": 0, "по имени": 0, "иначе": 0}
примеры = []
for inn in цель:
    р = s.execute(
        "SELECT cr.body, cr.subject, m.mailbox_id, r.email FROM messages m"
        " JOIN recipients r ON r.id=m.recipient_id"
        " JOIN confirm_reviews cr ON cr.message_id=m.id"
        " WHERE m.status='sent' AND m.campaign_id<>12 AND r.inn=? AND cr.body<>''"
        " ORDER BY m.sent_at DESC LIMIT 1", (inn,)).fetchone()
    if not р:
        ст["нет текста"] += 1
        continue
    т = str(р["body"])
    if "ИМЯ_ОТПРАВИТЕЛЯ" in т:
        ст["есть метка"] += 1
    else:
        ст["имя вместо метки"] += 1
        if len(примеры) < 3:
            примеры.append((inn, т.splitlines()[2][:80] if len(т.splitlines()) > 2
                            else т[:80]))
    п = т.strip().splitlines()[0]
    if re.match(r"^(добрый день|здравствуйте)", п, re.I):
        обращение["без имени"] += 1
    elif re.match(r"^[А-ЯЁ][а-яё]+", п) and "," in п[:30]:
        обращение["по имени"] += 1
    else:
        обращение["иначе"] += 1

print("\n=== ИСХОДНЫЙ ТЕКСТ ===")
for k, v in ст.items():
    print("  %-20s %d" % (k, v))
print("\n=== ОБРАЩЕНИЕ В ИСХОДНОМ ПИСЬМЕ ===")
for k, v in обращение.items():
    print("  %-14s %d" % (k, v))
print("\n=== ПРИМЕРЫ БЕЗ МЕТКИ ===")
for inn, стр in примеры:
    print("  %s: %s" % (inn, стр))
