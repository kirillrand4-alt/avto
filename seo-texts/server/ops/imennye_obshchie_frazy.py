# -*- coding: utf-8 -*-
"""Карточки «КЦ по имени» с ОБЩЕЙ фразой (модель не знала компанию: нет названия/деятельности
в enrich) — счёт pending/sent; --snyat снимает pending таких карточек."""
import io, json, re, sqlite3, sys
from datetime import datetime, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = c.execute("SELECT id FROM campaigns WHERE name='КЦ по имени 06.11'").fetchone()[0]
ОБЩ = re.compile(r"^На производстве сжатый воздух|технологических процесс", re.I)
сч = {}; ids = []
for i, st, b, п in c.execute("SELECT id, status, body, panel_json FROM confirm_reviews WHERE campaign_id=?", (кам,)):
    абз = (b or "").split("\n\n")
    ф = абз[1] if len(абз) > 1 else ""
    общ = bool(ОБЩ.search(ф))
    без_имени = not ((json.loads(п or "{}").get("company") or {}).get("name"))
    к = (st, "общая фраза" if общ else "своя фраза", "без названия" if без_имени else "")
    сч[к] = сч.get(к, 0) + 1
    if st == "pending" and общ: ids.append(i)
for к, v in sorted(сч.items()): print(к, v)
print("pending к снятию:", len(ids))
if "--snyat" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    with c:
        for i in ids:
            m = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?", (i,)).fetchone()[0]
            c.execute("UPDATE confirm_reviews SET status='skipped', reason='общая фраза: компания неизвестна генератору', decided_at=?, updated_at=? WHERE id=? AND status='pending'", (т, т, i))
            if m: c.execute("UPDATE messages SET status='skipped', last_error='общая фраза', updated_at=? WHERE id=? AND status='pending_review'", (т, m))
    print("снято")
