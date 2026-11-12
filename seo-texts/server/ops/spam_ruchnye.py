# -*- coding: utf-8 -*-
"""Отправки «ответом» (in_reply_to — из панели/скриптом, «мы ответили»): сколько за 10–12.11, по кампаниям/ящикам,
и были ли отказы «спам» — и при отправке (last_error), и отбивками (события bounce/dsn с «spam» в тексте). Только чтение."""
import json, re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
р = c.execute("SELECT id, campaign_id, mailbox_id, status, COALESCE(last_error,''), substr(COALESCE(sent_at, updated_at),1,10) FROM messages "
              "WHERE COALESCE(in_reply_to,'')<>'' AND COALESCE(sent_at, updated_at)>='2026-11-10'").fetchall()
print("писем-ответов с 10.11:", len(р), "| по дням:", sorted(Counter(x[5] for x in р).items()))
print("по статусам:", Counter(x[3] for x in р).most_common())
print("по кампаниям:", Counter("#%s %s" % (x[1], (кам.get(x[1]) or "")[:28]) for x in р).most_common(8))
сп = [x for x in р if re.search(r"(?i)спам|spam", x[4])]
print("отказ «спам» при отправке:", len(сп), Counter(x[2] for x in сп).most_common())
print("прочие ошибки:", Counter(x[4][:70] for x in р if x[3] == "failed" and x not in сп).most_common(6))
ids = {x[0] for x in р}
отб = Counter(); при = []
for mid, тип, dj in c.execute("SELECT message_id, event_type, detail_json FROM events WHERE event_type IN ('bounce','dsn','hard_bounce','soft_bounce') AND event_ts>='2026-11-10'"):
    if re.search(r"(?i)spam|спам", dj or ""):
        отб["ответ" if mid in ids else "первое письмо/прочее"] += 1
print("отбивки со словом spam с 10.11:", dict(отб))
print("типы событий с 10.11:", c.execute("SELECT event_type, COUNT(*) FROM events WHERE event_ts>='2026-11-10' GROUP BY 1 ORDER BY 2 DESC LIMIT 12").fetchall())
