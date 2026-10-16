import sqlite3, sys, time
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - int(sys.argv[2]) * 60))
print(",".join(str(r[0]) for r in c.execute("SELECT id FROM confirm_reviews WHERE campaign_id=? AND status='pending' AND created_at>=? ORDER BY id", (int(sys.argv[1]), от))))
