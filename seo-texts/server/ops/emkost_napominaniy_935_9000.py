# -*- coding: utf-8 -*-
"""Владелец 03.11: сколько напоминаний наберётся по «Партии 935» и «России 9000».
Компания: последнее письмо Meyer из этих кампаний > 15 дн. назад, писем любого
направления за 15 дн. нет, ни ответа/автоответа/жалобы/отбивки/лида, напоминания
не было (ни ушедшего, ни в очереди). Адрес — тот, куда ушло первое письмо;
годен только с пробой «есть»/«принимает всё». Только чтение."""
import collections, json, sqlite3
from datetime import datetime, timedelta, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
ЦЕЛЬ = {i for i, n in кам.items() if "935" in n or "9000" in n}
граница = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
проба = {e.lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
ответ = {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM events WHERE event_type IN ('reply','reply_auto','complaint','dsn','bounce')")}
ответ |= {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM leads")}
напом = {r[0] for r in c.execute("SELECT DISTINCT inn FROM confirm_reviews WHERE kind='reply' AND panel_json LIKE '%napominanie%' AND status IN ('sent','pending','approved') AND inn IS NOT NULL")}
комп = collections.defaultdict(list)
for mid, rid, cid, sa, инн, em in c.execute("SELECT m.id, m.recipient_id, m.campaign_id, m.sent_at, r.inn, lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at IS NOT NULL AND r.inn IS NOT NULL"):
    комп[инн].append((sa, cid, rid, em))
сч = collections.Counter()
for инн, пис in комп.items():
    пис.sort()
    наши = [x for x in пис if x[1] in ЦЕЛЬ and not str(кам.get(x[1], "")).lower().startswith("второе")]
    if not наши:
        continue
    к = ("935" if "935" in кам[наши[-1][1]] else "9000") + (" Meyer" if "meyer" in кам[наши[-1][1]].lower() else " КЦ")
    сч[(к, "всего компаний")] += 1
    if any(x[2] in ответ for x in пис):
        сч[(к, "отсев: был ответ/отбивка/лид")] += 1; continue
    if инн in напом:
        сч[(к, "отсев: напоминание уже было/в очереди")] += 1; continue
    if пис[-1][0] >= граница:
        сч[(к, "отсев: письмо за последние 15 дней")] += 1; continue
    в = проба.get(наши[0][3], "")
    if в in ("есть", "принимает всё"):
        сч[(к, "ГОДНО (адрес живой)")] += 1
    elif not в:
        сч[(к, "адрес без пробы")] += 1
    else:
        сч[(к, "адрес мёртв/неясно: " + в)] += 1
for к in sorted({x[0] for x in сч}):
    print("==", к)
    for (кк, ч), н in sorted(сч.items(), key=lambda x: -x[1]):
        if кк == к:
            print("   %6d  %s" % (н, ч))
