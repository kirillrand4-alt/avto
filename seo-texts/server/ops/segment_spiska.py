# -*- coding: utf-8 -*-
"""Сегменты карточек из списка и карта segment_division. --na=<сегмент> меняет сегмент (старый — в extra.segment_bylo)."""
import io, json, sqlite3, sys
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
рид = json.load(io.open(r"C:\sender\_ops\spisok-kc-iz-9000.json"))
сч = Counter(c.execute("SELECT segment FROM recipients WHERE id=?", (r,)).fetchone()[0] for r in рид)
print(сч.most_common(10))
на = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--na=")), None)
if на:
    with c:
        for r in рид:
            seg, ex = c.execute("SELECT segment, extra_json FROM recipients WHERE id=?", (r,)).fetchone()
            ex = json.loads(ex or "{}"); ex.setdefault("segment_bylo", seg)
            c.execute("UPDATE recipients SET segment=?, extra_json=? WHERE id=?", (на, json.dumps(ex, ensure_ascii=False), r))
    print("сменено на", на, len(рид))
