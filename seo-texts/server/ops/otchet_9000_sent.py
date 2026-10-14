# -*- coding: utf-8 -*-
"""Перепроверка «отправлено 3364» (владелец: «вроде около 2к»). Разделяем:
письмо ушло получателю ИЗ ГРУППЫ (recipient.extra_json несёт группу) против
письма той же компании из старых кампаний; по кампаниям и по датам."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
имя = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
for г in ("Россия 9000", "Белорусь 1000"):
    свои, чужие, по_камп, по_дню, комп = Counter(), Counter(), Counter(), Counter(), set()
    группа = {str(r[0]) for r in c.execute("SELECT inn FROM recipients WHERE extra_json LIKE ?", ("%" + г + "%",))}
    for inn, ex, кид, st, ts in c.execute(
            "SELECT r.inn, r.extra_json, m.campaign_id, m.status, COALESCE(m.sent_at, m.updated_at, m.created_at) "
            "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
        if str(inn) not in группа:
            continue
        if г in str(ex or ""):
            свои["письмо получателю группы"] += 1
            по_камп[имя.get(кид, кид)] += 1
            по_дню[str(ts or "")[:10]] += 1
            комп.add(str(inn))
        else:
            чужие[имя.get(кид, кид)] += 1
    print("== %s: отправлено по группе %d писем, %d компаниям; той же компании из ДРУГИХ кампаний %d" % (
        г, свои["письмо получателю группы"], len(комп), sum(чужие.values())))
    for k, n in по_камп.most_common(8):
        print("   кампания %-40s %5d" % (str(k)[:40], n))
    print("   по дням:", dict(sorted(по_дню.items())))
    print("   другие кампании:", dict(чужие.most_common(8)))
print("=== ОТПРАВЛЕНО 9000 ===")
