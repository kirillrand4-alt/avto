# -*- coding: utf-8 -*-
"""Состав pending-очереди подтверждения: вид (напоминание/ответ/холодное) × кампания × день создания."""
import collections, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
сч = collections.Counter()
for k, cid, п, cr in c.execute("SELECT kind, campaign_id, COALESCE(panel_json,''), substr(created_at,1,10) FROM confirm_reviews WHERE status='pending'"):
    вид = "напоминание-заход" if "заходы" in п else ("напоминание" if "napominanie" in п else k)
    сч[(вид, кам.get(cid, "-"), cr)] += 1
print("всего pending:", sum(сч.values()))
for к, н in сч.most_common(20):
    print("%5d  %s" % (н, к))
