# -*- coding: utf-8 -*-
"""Куда ушли карточки из очереди подтверждения за последние N часов: статус × причина/оператор."""
import collections, sqlite3, sys
Ч = int(sys.argv[1]) if len(sys.argv) > 1 else 6
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
cols = [r[1] for r in c.execute("PRAGMA table_info(confirm_reviews)")]
оп = "operator" if "operator" in cols else ("decided_by" if "decided_by" in cols else "''")
сч = collections.Counter()
for st, kind, rs, o, п in c.execute("SELECT status, kind, COALESCE(reason,''), COALESCE(%s,''), COALESCE(panel_json,'') FROM confirm_reviews "
                                    "WHERE decided_at >= datetime('now', ?)" % оп, ("-%d hours" % Ч,)):
    вид = "напоминание" if "napominanie" in п else kind
    сч[(st, вид, rs[:70], o[:45])] += 1
for к, н in сч.most_common(25):
    print("%5d  %s" % (н, к))
print("pending сейчас:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'").fetchone()[0])
