# -*- coding: utf-8 -*-
"""Владелец 17.11: «сними старые карточки, оставь новые». Адреса, у которых есть карточка в «Meyer провалы 17.11»
(pending) и одновременно неотправленная карточка в другой кампании (pending/approved) — старую карточку и её письмо
переводим в skipped. Журнал _ops/meyer-snyato-starye-1711.jsonl (fsync).   meyer_snyat_starye_1711.py [--primenit]"""
import io, json, os, sqlite3, sys, time
from collections import Counter
т = time.strftime("%Y-%m-%dT%H:%M:%S"); ПРИЧ = "дубль: адрес в кампании «Meyer провалы 17.11» (владелец 17.11)"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
К = c.execute("SELECT id FROM campaigns WHERE name='Meyer провалы 17.11'").fetchone()[0]
стар = c.execute("SELECT cr.id, cr.message_id, cr.status, cr.campaign_id, lower(cr.email) FROM confirm_reviews cr WHERE cr.campaign_id<>? "
                 "AND cr.status IN ('pending','approved') AND lower(cr.email) IN (SELECT lower(email) FROM confirm_reviews WHERE campaign_id=? AND status='pending')",
                 (К, К)).fetchall()
по_камп = Counter(dict(c.execute("SELECT id, name FROM campaigns").fetchall()).get(r[3]) for r in стар)
print("старых карточек: %d, адресов %d | по кампаниям %s | статусы %s" % (len(стар), len({r[4] for r in стар}), dict(по_камп), dict(Counter(r[2] for r in стар))))
if "--primenit" in sys.argv:
    with c, io.open(r"C:\sender\_ops\meyer-snyato-starye-1711.jsonl", "a", encoding="utf-8") as ж:
        for кид, mid, ст, камп, em in стар:
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status IN ('pending','approved')", (ПРИЧ, т, т, кид))
            if mid: c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('pending_review','approved','scheduled')", (ПРИЧ, т, mid))
            ж.write(json.dumps({"karta": кид, "message": mid, "bylo": ст, "kampaniya": камп, "email": em, "ts": т}, ensure_ascii=False) + "\n")
        ж.flush(); os.fsync(ж.fileno())
    print("СНЯТО:", len(стар))
