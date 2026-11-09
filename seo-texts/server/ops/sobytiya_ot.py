# -*- coding: utf-8 -*-
"""События по адресу отправителя (в detail_json): sobytiya_ot.py АДРЕС [...]. Только чтение."""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
for a in sys.argv[1:]:
    print("==", a)
    for r in c.execute("SELECT id, event_type, recipient_id, mailbox_id, event_ts, detail_json, dedup_key FROM events WHERE detail_json LIKE ? ORDER BY id DESC LIMIT 5", ("%" + a + "%",)):
        д = json.loads(r[5] or "{}")
        print("  #%s %s rid=%s %s %s dedup=%s" % (r[0], r[1], r[2], r[3], r[4][:16], r[6][:40]))
        print("     ключи:", list(д)[:20]); print("     ", {k: str(v)[:160] for k, v in д.items() if k in ("subject", "snippet", "from", "body", "text", "thread_id")})
