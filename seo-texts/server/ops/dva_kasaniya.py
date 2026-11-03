# -*- coding: utf-8 -*-
"""Компании, у которых в одно окно и напоминание (карточка kind=reply napominanie),
и второе касание лесенки (messages с темой Re: после 31.10) — sent/pending."""
import collections, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
нап = collections.defaultdict(list)
for i, инн, e, st, d in c.execute("SELECT id, inn, email, status, decided_at FROM confirm_reviews WHERE kind='reply' "
                                  "AND panel_json LIKE '%napominanie%' AND status IN ('pending','sent') AND inn IS NOT NULL"):
    нап[инн].append((i, e, st, (d or "")[:16]))
лес = collections.defaultdict(list)
for mid, инн, e, st, sa, mb in c.execute("SELECT m.id, r.inn, r.email, m.status, m.sent_at, m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                         "WHERE m.subject LIKE 'Re:%' AND m.created_at >= '2026-10-31' AND m.status NOT IN ('cancelled','failed','skipped')"):
    лес[инн].append((mid, e, st, (sa or "")[:16], mb))
# строка messages, совпадающая с карточкой по адресу и минуте, — это сама отправка напоминания
for инн in list(лес):
    свои = {(x[1].lower(), x[3]) for x in нап.get(инн, [])}
    лес[инн] = [y for y in лес[инн] if (y[1].lower(), y[3]) not in свои]
    if not лес[инн]:
        del лес[инн]
оба = [инн for инн in нап if инн in лес]
сч = collections.Counter()
for инн in оба:
    к = ("напоминание " + "/".join(sorted({x[2] for x in нап[инн]})), "лесенка " + "/".join(sorted({x[2] for x in лес[инн]})))
    сч[к] += 1
print("компаний с напоминанием:", len(нап), "| с лесенкой после 31.10:", len(лес), "| и то и другое:", len(оба))
for к, н in сч.most_common():
    print("  ", н, к)
for инн in оба[:6]:
    print(инн, нап[инн], лес[инн])
