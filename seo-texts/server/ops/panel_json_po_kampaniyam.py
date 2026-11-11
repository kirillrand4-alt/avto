# -*- coding: utf-8 -*-
"""Какие блоки panel_json у карточек по кампаниям (ключи и ключи company), сколько ушло писем кампании.
Только чтение.  panel_json_po_kampaniyam.py [кампании через запятую]"""
import json, sqlite3, sys
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
кмп = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [r[0] for r in c.execute("SELECT DISTINCT campaign_id FROM confirm_reviews WHERE kind='outbound' ORDER BY campaign_id DESC LIMIT 12")]
for к in кмп:
    имя = (c.execute("SELECT name FROM campaigns WHERE id=?", (к,)).fetchone() or [""])[0]
    кл, ккл = Counter(), Counter()
    for (pj,) in c.execute("SELECT panel_json FROM confirm_reviews WHERE campaign_id=? ORDER BY id DESC LIMIT 50", (к,)):
        д = json.loads(pj or "{}"); кл.update(д.keys())
        if isinstance(д.get("company"), dict): ккл.update(д["company"].keys())
    ушло = c.execute("SELECT COUNT(*) FROM send_log WHERE campaign_id=? AND outcome='sent'", (к,)).fetchone()[0]
    ст = dict(c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=? GROUP BY status", (к,)).fetchall())
    print("%3d %-30s ушло %5d | карточки %s\n     ключи: %s\n     company: %s" % (к, имя[:30], ушло, ст, sorted(кл), sorted(ккл)))
