# -*- coding: utf-8 -*-
"""Кампания: письма со станцией «под резку» — у скольких фраза про компанию вообще о резке. Только чтение.  <id>"""
import json, sqlite3, sys
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
сч = Counter(); отр = Counter()
for т, pj in c.execute("SELECT COALESCE(edited_body, body), panel_json FROM confirm_reviews WHERE campaign_id=? AND status IN ('pending','approved')", (int(sys.argv[1]),)):
    if "станции под резку" not in т: continue
    абз = т.split("\n\n")[1]
    сч["фраза о резке" if "рез" in абз.split("Мы как раз")[0].lower() else "фраза НЕ о резке"] += 1
    отр[(json.loads(pj or "{}").get("gaz") or {}).get("otrasl", "")[:50]] += 1
print(dict(сч)); print(отр.most_common(8))
