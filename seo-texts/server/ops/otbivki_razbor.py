# -*- coding: utf-8 -*-
"""Отбивки (bounce) и reject_spam с 10.11: причины по коду/тексту DSN, по видам писем (ответ / первое). Только чтение."""
import json, re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
отв = {r[0] for r in c.execute("SELECT id FROM messages WHERE COALESCE(in_reply_to,'')<>''")}
сч = Counter(); ключи = Counter()
for mid, тип, dj in c.execute("SELECT message_id, event_type, detail_json FROM events WHERE event_type IN ('bounce','reject_spam') AND event_ts>='2026-11-10'"):
    д = json.loads(dj or "{}"); ключи.update(д.keys())
    dsn = д.get("dsn") or {}
    текст = " ".join(str(x) for x in (dsn.get("diagnostic"), dsn.get("status"), dsn.get("verdict"), д.get("reason"), д.get("error"), д.get("snippet")) if x)
    кат = ("спам" if re.search(r"(?i)spam|спам", текст) else "нет ящика/адреса" if re.search(r"(?i)user unknown|no such|does not exist|не существ|5\.1\.1|not found|unknown", текст)
           else "ящик переполнен" if re.search(r"(?i)quota|full|переполн|storage", текст) else "прочее")
    сч[(тип, "ответ" if mid in отв else "первое/прочее", кат)] += 1
print("ключи detail:", ключи.most_common(12))
for к, v in сч.most_common(): print("  ", к, v)
