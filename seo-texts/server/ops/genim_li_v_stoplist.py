# -*- coding: utf-8 -*-
"""Генерируются ли письма на адреса из стоп-листа — и уходят ли они."""
import sqlite3
from collections import Counter
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== ЧЕРНОВИКИ (confirm_reviews), чей адрес есть в стоп-листе ===")
всего = c.execute("SELECT COUNT(*) FROM confirm_reviews").fetchone()[0]
строки = list(c.execute(
    "SELECT cr.id, cr.status, cr.kind, cr.email, s.reason, "
    "       substr(COALESCE(cr.decided_at, cr.updated_at),1,10) д, "
    "       s.created_at сд "
    "  FROM confirm_reviews cr "
    "  JOIN suppression s ON LOWER(s.value) = LOWER(cr.email)"))
print("черновиков всего: %d, из них на адрес из стоп-листа: %d"
      % (всего, len(строки)))
по_статусу, по_причине, по_дням = Counter(), Counter(), Counter()
раньше = позже = 0
for r in строки:
    по_статусу[r["status"]] += 1
    по_причине[str(r["reason"])[:34]] += 1
    по_дням[str(r["д"])] += 1
    # адрес попал в стоп-лист ДО того, как сгенерировали письмо, или после?
    if str(r["сд"] or "") and str(r["д"] or ""):
        if str(r["сд"])[:10] <= str(r["д"]):
            раньше += 1
        else:
            позже += 1
print("  по статусу:  %s" % dict(по_статусу))
print("  по причине:  %s" % dict(по_причине.most_common(8)))
print("  стоп-лист был РАНЬШЕ письма: %d, появился ПОЗЖЕ: %d" % (раньше, позже))
print("  по дням (последние): %s"
      % dict(sorted(по_дням.items())[-8:]))
ушли = [r for r in строки if r["status"] == "sent"]
print("\n  реально ОТПРАВЛЕНО на адрес из стоп-листа: %d" % len(ушли))
for r in ушли[:12]:
    print("     review=%-7s %s %-34s причина: %s"
          % (r["id"], r["д"], r["email"], str(r["reason"])[:34]))

print("\n=== ЖИВАЯ ОЧЕРЕДЬ прямо сейчас ===")
for статус in ("pending_review", "approved"):
    n = c.execute(
        "SELECT COUNT(*) FROM confirm_reviews cr "
        "  JOIN suppression s ON LOWER(s.value)=LOWER(cr.email) "
        " WHERE cr.status=?", (статус,)).fetchone()[0]
    всего_с = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status=?",
                        (статус,)).fetchone()[0]
    print("   %-16s всего %5d, из них в стоп-листе %d" % (статус, всего_с, n))
n = c.execute(
    "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "  JOIN suppression s ON LOWER(s.value)=LOWER(r.email) "
    " WHERE m.status IN ('scheduled','sending')").fetchone()[0]
print("   писем в очереди отправки на адрес из стоп-листа: %d" % n)
print("\n=== события «адрес в стоп-листе» (заслон сработал) ===")
for r in c.execute("SELECT substr(event_ts,1,10) д, COUNT(*) n FROM events "
                   " WHERE event_type='suppress' GROUP BY 1 ORDER BY 1 DESC "
                   " LIMIT 8"):
    print("   %s  %d" % (r["д"], r["n"]))
c.close()
