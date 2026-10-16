import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
кол = [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")]; print("addr_probe:", кол)
tsk = next((k for k in ("ts", "checked_at", "updated_at", "created_at") if k in кол), None)
сч = Counter()
for em, sent, pts, v in c.execute(
        "SELECT r.email, m.sent_at, p.%s, p.verdict FROM events e JOIN recipients r ON r.id=e.recipient_id "
        "JOIN messages m ON m.id=e.message_id JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        "WHERE e.event_type='bounce' AND e.event_ts>='2026-10-15' AND p.verdict IN ('нет ящика','нет MX')" % tsk):
    k = "вердикт ДО отправки" if str(pts) < str(sent) else "вердикт ПОСЛЕ отправки"
    сч[k] += 1
    if k.startswith("вердикт ДО"): print(em, "проба", pts, "отправка", sent)
print(dict(сч))
print("16.10 по направлению КЦ: отправлено", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>='2026-10-16' AND campaign_id IN (1,5,6,10,15,16)").fetchone()[0],
      "Meyer", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>='2026-10-16' AND campaign_id IN (8,11,14)").fetchone()[0])
