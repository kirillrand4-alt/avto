# -*- coding: utf-8 -*-
"""Дописать ответ (событие) в существующий лид штатным путём create_lead с ключом
этого лида («второй ответ дописывает карточку»), лишний отдельный лид — в deleted.
Владелец 14.10: «добавь просто ещё одно письмо к существующему».

    dopisat_v_lid.py <event_id> <lead_id_куда> [<lead_id_убрать>]
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

eid, куда = int(sys.argv[1]), int(sys.argv[2])
убрать = int(sys.argv[3]) if len(sys.argv) > 3 else None
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
д = json.loads(е["detail_json"] or "{}")
от = str((д.get("headers") or {}).get("From") or "")
адрес = (re.findall(r"[\w.+-]+@[\w.-]+", от) or [""])[0].lower()
текст = re.split(r"-----Original Message-----|\nFrom:|\nОт:", str(д.get("snippet") or ""))[0].strip()
л = c.execute("SELECT * FROM leads WHERE id=?", (куда,)).fetchone()
store = Store(r"C:\sender\sender.db")
need = "Ответ %s (%s): «%s»" % (от.split("<")[0].strip().strip('"') or адрес, адрес, re.sub(r"\s+", " ", текст)[:500])
_id, создан = store.create_lead(email=л["email"], dedup_key=л["dedup_key"], reply_kind=д.get("reply_kind"), need=need)
print("дописано в лид #%s (создан заново: %s)" % (_id, создан))
print("начало карточки:", str(c.execute("SELECT need FROM leads WHERE id=?", (куда,)).fetchone()[0])[:220])
if убрать:
    т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        c.execute("UPDATE leads SET status='deleted', updated_at=? WHERE id=?", (т, убрать))
        c.execute("INSERT INTO lead_events (lead_id, action, to_status, created_at) VALUES (?, ?, 'deleted', ?)",
                  (убрать, "снят: ответ дописан в лид #%d" % куда, т))
    print("лид #%d снят (deleted)" % убрать)
print("=== ДОПИСАТЬ В ЛИД ===")
