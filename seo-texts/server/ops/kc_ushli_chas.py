import sqlite3, time
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3 * 3600))
for r in c.execute("SELECT substr(m.sent_at,1,16), m.mailbox_id, m.campaign_id, r.email, m.subject FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.status='sent' AND m.sent_at>=? AND (m.mailbox_id LIKE '%compressor-%' OR m.mailbox_id LIKE '%kompressor-%') ORDER BY m.sent_at", (от,)):
    print(r)
print(c.execute("SELECT campaign_id, status, COUNT(*) FROM messages WHERE status IN ('scheduled','approved','sending') AND campaign_id IN (1,5,6,10,15,16) GROUP BY 1,2").fetchall())
