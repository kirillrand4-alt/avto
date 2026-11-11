# -*- coding: utf-8 -*-
"""Письма кампании 22, где фраза про их процесс об одном газе, а станция/вопрос — о другом (линза «адресат» 11.11:
«газ — азот, письмо про кислород для озонатора»). Только чтение.  [--primery]"""
import re, sqlite3, sys
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
сч = Counter(); прим = []
for кид, тело in c.execute("SELECT id, COALESCE(edited_body, body) FROM confirm_reviews WHERE campaign_id=22 AND status='pending'"):
    абз = (тело or "").split("\n\n")
    if len(абз) < 4: continue
    м = re.search(r"\s(Под такие задачи|Для этого|Под такие процессы|Под резку)\b", абз[1])
    фраза = абз[1][:м.start()] if м else абз[1]
    хвост = абз[1][м.start():] if м else абз[1]
    станц = "O2" if re.search(r"(?i)кислород", хвост) else "N2"   # «проекты по кислороду» — без «кислородн» (ошибка 11.11)
    в_фразе = "O2" if re.search(r"(?i)кислород|озон", фраза) and not re.search(r"(?i)\bазот", фраза) else ("N2" if re.search(r"(?i)\bазот", фраза) else "?")
    if в_фразе != "?" and в_фразе != станц:
        сч["фраза %s, станция %s" % (в_фразе, станц)] += 1
        if len(прим) < 6: прим.append((кид, фраза[:160]))
    else:
        сч["согласовано" if в_фразе != "?" else "газ во фразе не назван"] += 1
print(dict(сч))
for п in прим: print(" #%s %s" % п)

# снятые линзой «верной фразы про наш газ нет»: сколько из них на деле кислородные письма
сн = c.execute("SELECT id, COALESCE(edited_body, body) FROM confirm_reviews WHERE campaign_id=22 AND status='skipped' AND reason LIKE 'линза:%'").fetchall()
кисл = [кид for кид, т in сн if re.search(r"(?i)кислород", (т or "").split("\n\n")[1] if (т or "").count("\n\n") >= 3 else "")]
print("снято линзой всего: %d, из них кислородные письма: %d -> %s" % (len(сн), len(кисл), кисл[:40]))
