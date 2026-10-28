# -*- coding: utf-8 -*-
"""Итог пилота напоминаний: ответы/автоответы/отбивки/жалобы после отправки
напоминания, по заходам; лиды и их вид. Контроль — компании, подходившие под
напоминание, но не попавшие в пилот: сколько из них ответило за то же время. Только чтение."""
import io
import json
import sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
пил_инн = {x["inn"] for x in з}
когда = {}
for x in з:
    r = c.execute("SELECT decided_at, status FROM confirm_reviews WHERE id=?", (x["karta"],)).fetchone()
    когда[x["inn"]] = (r[0] or "") if r else ""
по_инн_rid = defaultdict(set)
for rid, inn in c.execute("SELECT id, inn FROM recipients WHERE inn IS NOT NULL"):
    по_инн_rid[str(inn)].add(rid)
ТИПЫ = ("reply", "reply_auto", "bounce", "dsn", "complaint", "reject_spam")
итог = defaultdict(Counter)
примеры = []
for x in з:
    инн, с = x["inn"], когда.get(x["inn"]) or "2026-10-26"
    rids = по_инн_rid.get(инн, set())
    if not rids:
        continue
    q = ",".join(map(str, rids))
    события = c.execute("SELECT event_type, event_ts, id, substr(coalesce(detail_json,''),1,400) FROM events WHERE recipient_id IN (%s) "
                        "AND event_type IN ('reply','reply_auto','bounce','dsn','complaint','reject_spam') AND event_ts >= ?" % q, (с[:19],)).fetchall()
    типы = {e[0] for e in события}
    з_ = x["zahod"]
    итог[з_]["отправлено"] += 1
    for t in ТИПЫ:
        if t in типы:
            итог[з_][t] += 1
    if "reply" in типы:
        лид = c.execute("SELECT reply_kind, status FROM leads WHERE inn=? ORDER BY id DESC LIMIT 1", (инн,)).fetchone()
        итог[з_]["вид: " + str(лид[0] if лид else "нет лида")] += 1
        ev = [e for e in события if e[0] == "reply"][0]
        try:
            сн = json.loads(c.execute("SELECT detail_json FROM events WHERE id=?", (ev[2],)).fetchone()[0] or "{}").get("snippet", "")
        except Exception:  # noqa: BLE001
            сн = ""
        примеры.append("заход %s | %s | %s | %s" % (з_, x["email"], лид[0] if лид else "-", " ".join(str(сн).split())[:160]))
всего = Counter()
for з_, сч in sorted(итог.items()):
    всего.update(сч)
    print("заход %s: %s" % (з_, dict(сч)))
print("ВСЕГО:", dict(всего))
# контроль: подходившие под напоминание (Meyer, последнее письмо до 11.10, без ответов до 26.10), не в пилоте
кам = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower()]
контроль = set()
for inn, посл in c.execute("SELECT r.inn, MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                           "WHERE m.status='sent' AND m.campaign_id IN (%s) AND r.inn IS NOT NULL GROUP BY r.inn" % ",".join(map(str, кам))):
    if inn and посл and посл < "2026-10-11" and str(inn) not in пил_инн:
        контроль.add(str(inn))
ответили_до = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                             "WHERE e.event_type IN ('reply','reply_auto','complaint') AND e.event_ts < '2026-10-26'")}
контроль -= ответили_до
отв_после = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                           "WHERE e.event_type='reply' AND e.event_ts >= '2026-10-26'")}
n = len(контроль & отв_после)
print("КОНТРОЛЬ (не получали напоминание): компаний %d, ответили сами после 26.10: %d (%.1f%%)" % (len(контроль), n, 100.0 * n / max(1, len(контроль))))
print("\nОТВЕТЫ:")
print("\n".join(примеры))
