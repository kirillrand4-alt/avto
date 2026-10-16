# -*- coding: utf-8 -*-
"""Сменить статус лида: lid_status.py <id> <статус> "<почему>" (с событием в lead_events)."""
import json, sqlite3, sys, time
lid, st, why = int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
было = c.execute("SELECT status FROM leads WHERE id=?", (lid,)).fetchone()[0]
т = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
with c:
    c.execute("UPDATE leads SET status=?, version=version+1, updated_at=? WHERE id=?", (st, т, lid))
    c.execute("INSERT INTO lead_events (lead_id, action, from_status, to_status, detail_json, created_at) VALUES (?, 'status_changed', ?, ?, ?, ?)",
              (lid, было, st, json.dumps({"status": st, "pochemu": why}, ensure_ascii=False), т))
print("лид", lid, было, "->", st)
