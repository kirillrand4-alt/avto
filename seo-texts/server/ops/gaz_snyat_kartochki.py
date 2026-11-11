# -*- coding: utf-8 -*-
"""Снять pending-карточки кампании 22 по списку id с причиной (сообщение → skipped).
    gaz_snyat_kartochki.py <файл со списком id на дропе> "причина" [--primenit]"""
import io, os, sqlite3, sys
from datetime import datetime, timezone
ids = [int(x) for x in io.open(os.path.join(r"C:\seostat\drop\drop-storage", sys.argv[1]), encoding="utf-8").read().replace("\n", ",").split(",") if x.strip()]
ПРИЧ = sys.argv[2]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
n = 0
for кид in ids:
    р = c.execute("SELECT status, message_id FROM confirm_reviews WHERE id=? AND campaign_id=22", (кид,)).fetchone()
    if not р or р[0] != "pending": continue
    n += 1
    if "--primenit" in sys.argv:
        c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", (ПРИЧ[:200], т, т, кид))
        if р[1]: c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')", (ПРИЧ[:100], р[1]))
if "--primenit" in sys.argv: c.commit()
print("%s: %d из %d" % ("снято" if "--primenit" in sys.argv else "к снятию", n, len(ids)))
print("pending в кампании 22:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchone()[0])
