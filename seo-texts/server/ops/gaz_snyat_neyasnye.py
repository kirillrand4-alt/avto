# -*- coding: utf-8 -*-
"""Снять из кампании 22 письма на адреса с вердиктом пробы «неясно» и «отказ пробе» (владелец 12.11: «этих сними»).
Снимает и pending-карточки, и уже одобренные (сообщение scheduled); отправленные не трогает — только считает.
Журнал _ops/gaz-snyat-neyasnye.jsonl.   gaz_snyat_neyasnye.py [--primenit]"""
import io, json, os, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
ПРИМ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
вер = {em: v for em, v in c.execute("SELECT lower(email), verdict FROM addr_probe")}
жур = io.open(r"C:\sender\_ops\gaz-snyat-neyasnye.jsonl", "a", encoding="utf-8")
сч = Counter()
for кид, em, ст, мид in c.execute("SELECT id, lower(email), status, message_id FROM confirm_reviews WHERE campaign_id=22 AND status IN ('pending','approved')").fetchall():
    v = вер.get(em, "")
    if v not in ("неясно", "отказ пробе"): continue
    мст = c.execute("SELECT status FROM messages WHERE id=?", (мид,)).fetchone() if мид else None
    мст = мст[0] if мст else ""
    if мст == "sent": сч["уже отправлено (%s)" % v] += 1; continue
    сч["снять (%s, карточка %s)" % (v, ст)] += 1
    if ПРИМ:
        причина = "проба: %s (владелец 12.11)" % v
        c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status IN ('pending','approved')", (причина, т, т, кид))
        if мид: c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')", (причина, мид))
        жур.write(json.dumps({"karta": кид, "email": em, "verdict": v, "byl_status": ст, "msg_status": мст, "ts": т}, ensure_ascii=False) + "\n")
if ПРИМ: c.commit(); жур.flush(); os.fsync(жур.fileno())
print("%s: %s" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон", dict(сч)))
print("карточки:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=22 GROUP BY status").fetchall())
print("сообщения:", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=22 GROUP BY status").fetchall())
