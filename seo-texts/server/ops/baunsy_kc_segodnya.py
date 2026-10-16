import json, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
for em, dj, src in c.execute(
        "SELECT r.email, e.detail_json, r.source FROM events e JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type='bounce' AND e.event_ts>='2026-10-16' AND e.campaign_id IN (1,5,6,10,15,16)"):
    d = json.loads(dj or "{}"); dsn = d.get("dsn") or {}
    print(em, "|", str(dsn.get("status") or ""), "|", str(dsn.get("diagnostic") or "")[:110].replace("\n", " "))
