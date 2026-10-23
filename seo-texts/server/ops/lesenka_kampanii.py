# -*- coding: utf-8 -*-
"""Лесенка по кампании (владелец 23.10: «сколько здесь почт по лесенке вторых?
кому можно написать из тех, кто не ответил»): компании, которым кампания
писала и которые НЕ ответили (нет лида, ответа, автоответа). Следующий адрес —
enrich.emails компании: ещё не писали, не стоп-лист, не мёртв/неясно/отказ,
роль > 1 и не кадры/бухгалтерия, не числится за другим ИНН в панели.
Разрез: по пробе лучшего запасного, свой домен/публичный, роль; когда пройдёт
30 дней с последнего письма направления. Пишет _ops/lesenka-<id>.json.
    lesenka_kampanii.py <campaign_id>"""
import io
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4
cid = int(sys.argv[1])
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|финанс|hr|резюме|не для письма")
ПУБ = ("mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru")
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
получ = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, inn FROM recipients")}
писали = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log WHERE outcome='sent'")}
писали |= {str(r[0]).lower() for r in c.execute("SELECT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                               "WHERE m.status NOT IN ('skipped','failed')")}
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
ответ |= {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id "
                                       "WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
комп = {}
for inn, sa in c.execute("SELECT r.inn, MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                         "WHERE m.campaign_id=? AND m.status='sent' AND r.inn IS NOT NULL GROUP BY r.inn", (cid,)):
    комп[str(inn)] = str(sa)
сч, вер, дом, роли, итог = Counter(), Counter(), Counter(), Counter(), []
for inn, sa in комп.items():
    if inn in ответ:
        сч["ответили"] += 1
        continue
    сч["не ответили"] += 1
    канд = []
    for а, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
        роль = str(роль or "")
        if not а or а in писали or а in стоп or а.split("@")[-1] in стоп:
            continue
        if ПЛОХО.search(роль) or ПЛОХО.search(а.split("@")[0]) or _rol_ball(роль) <= 1:
            continue
        if проба.get(а) in ("нет ящика", "нет MX", "неясно", "отказ пробе"):
            continue
        if а in получ and получ[а] != inn:
            continue
        канд.append(({"есть": 0, "принимает всё": 1}.get(проба.get(а, ""), 2), -_rol_ball(роль), а, роль))
    if not канд:
        сч["  запасного нет"] += 1
        continue
    канд.sort()
    в, _, а, роль = канд[0]
    сч["  есть следующий адрес"] += 1
    вер[{0: "есть", 1: "принимает всё", 2: "не проверен"}[в]] += 1
    дом["публичный" if а.split("@")[-1] in ПУБ else "свой домен"] += 1
    роли[роль.split("|")[0].strip()[:30] or "—"] += 1
    итог.append({"inn": inn, "email": а, "role": роль, "posl_pismo": sa[:10], "vsego_zapasnyh": len(канд)})
print("компаний в кампании:", len(комп))
for k, v in сч.items():
    print("  %-28s %d" % (k, v))
print("запасной по пробе:", dict(вер))
print("домен:", dict(дом))
print("роль:", роли.most_common(10))
print("компаний с 2+ запасными:", sum(1 for x in итог if x["vsego_zapasnyh"] >= 2))
print("последнее письмо:", Counter(x["posl_pismo"] for x in итог).most_common(6))
json.dump(итог, io.open(r"C:\sender\_ops\lesenka-%d.json" % cid, "w", encoding="utf-8"), ensure_ascii=False)
