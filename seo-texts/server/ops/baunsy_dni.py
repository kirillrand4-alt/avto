# -*- coding: utf-8 -*-
"""Отказы (bounce) по дням: тип, кампания/направление, домен-отправитель, домен получателя, вердикт пробы. Только чтение."""
import json, re, sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
проба = {str(e).lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
по = defaultdict(Counter)
for ts, cid, mb, dj, em in c.execute(
        "SELECT substr(e.event_ts,1,10), e.campaign_id, e.mailbox_id, e.detail_json, r.email FROM events e "
        "LEFT JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type='bounce' AND e.event_ts>='2026-10-13'"):
    d = json.loads(dj or "{}"); dsn = d.get("dsn") or {}
    тип = str(dsn.get("kind") or dsn.get("type") or d.get("kind") or "?")
    диаг = str(dsn.get("diagnostic") or d.get("diagnostic") or "")
    if re.search(r"(?i)spam|спам", диаг): тип += "/спам"
    elif re.search(r"(?i)no such user|user unknown|not exist|не существ|mailbox unavailable|5\.1\.1", диаг): тип += "/нет ящика"
    elif re.search(r"(?i)quota|over|переполн|5\.2\.2", диаг): тип += "/переполнен"
    по[ts]["тип " + тип] += 1
    по[ts]["направл " + ("Meyer" if "Meyer" in str(кам.get(cid)) else "КЦ")] += 1
    по[ts]["проба " + str(проба.get(str(em or "").lower(), "не проверен"))] += 1
    по[ts]["отпр.домен " + str(mb or "?").split("@")[-1]] += 1
for d in sorted(по):
    print("\n==", d, sum(v for k, v in по[d].items() if k.startswith("тип ")))
    for k, v in по[d].most_common(): print("   %3d %s" % (v, k))
