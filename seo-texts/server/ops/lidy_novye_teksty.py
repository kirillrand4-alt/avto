# -*- coding: utf-8 -*-
"""Лиды в статусе «новый» с текстом ответа (events.detail_json.snippet по source_event_id, иначе need) — для разбора
владельцем 19.11 «если полный отказ и нет запроса на доп. услуги — в не интересно». Только чтение; полный вывод —
в _ops/lidy-novye.txt (скачать через дроп), на экран — счёт по reply_kind.   lidy_novye_teksty.py"""
import io, json, sqlite3
from collections import Counter
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True); к.row_factory = sqlite3.Row
кам = dict(к.execute("SELECT id, name FROM campaigns").fetchall())
лл = к.execute("SELECT * FROM leads WHERE status='new' ORDER BY id").fetchall()
print("новых лидов:", len(лл), dict(Counter(l["reply_kind"] for l in лл)))
with io.open(r"C:\sender\_ops\lidy-novye.txt", "w", encoding="utf-8") as ф:
    for l in лл:
        т = ""
        if l["source_event_id"]:
            e = к.execute("SELECT detail_json FROM events WHERE id=?", (l["source_event_id"],)).fetchone()
            try: т = (json.loads(e["detail_json"] or "{}") or {}).get("snippet") or "" if e else ""
            except Exception: т = ""
        ф.write("=== лид %d | %s | %s | %s | кампания %s | %s\n%s\n\n" % (l["id"], l["reply_kind"], l["company_name"], l["email"],
                кам.get(l["campaign_id"], l["campaign_id"]), str(l["created_at"])[:16], (т or l["need"] or "")[:1500]))
print("записано в _ops/lidy-novye.txt")
