# -*- coding: utf-8 -*-
"""Починка разнобоя газа в письмах кампании 22 (11.11): фраза про кислород/озонатор, а станция/вопрос/тема — азотные
(в файле ЦА у части водоканалов и розлива воды газ «азот» при отрасли «озонирование»). Фраза остаётся; станция —
кислородная (канон gaz_kanon.ОХВАТ["O2"]), в вопросе «кислородной станции», тема из ТЕМЫ["O2"], panel gaz.gaz=O2.
    gaz_pochinit_gaz.py [--primenit]"""
import json, os, random, re, sqlite3, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K   # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
n = 0; пример = None
for кид, тело, ed, pj in c.execute("SELECT id, body, edited_body, panel_json FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall():
    if ed and ed != тело: continue
    абз = (тело or "").split("\n\n")
    if len(абз) < 4: continue
    м = re.search(r"\s(Под такие задачи|Для этого|Под такие процессы|Под резку)\b", абз[1])
    if not м: continue
    фраза, хвост = абз[1][:м.start()].strip(), абз[1][м.start():]
    if not (re.search(r"(?i)кислород|озон", фраза) and not re.search(r"(?i)\bазот", фраза) and "азотн" in хвост): continue
    абз[1] = фраза + " " + random.choice(K.ОХВАТ["O2"])
    абз[3] = абз[3].replace("азотной станции", "кислородной станции")
    новое = "\n\n".join(абз)
    тема = random.choice(K.ТЕМЫ["O2"])
    д = json.loads(pj or "{}")
    if isinstance(д.get("gaz"), dict): д["gaz"]["gaz"] = "O2"; д["gaz"]["pochineno"] = "газ письма переведён на кислород (11.11)"
    n += 1
    if пример is None: пример = (кид, тема, новое)
    if "--primenit" in sys.argv:
        c.execute("UPDATE confirm_reviews SET body=?, subject=?, panel_json=?, updated_at=? WHERE id=? AND status='pending'",
                  (новое, тема, json.dumps(д, ensure_ascii=False), т, кид))
if "--primenit" in sys.argv: c.commit()
print("%s: %d" % ("исправлено" if "--primenit" in sys.argv else "к исправлению", n))
if пример: print("пример #%s\nТема: %s\n%s" % пример)
