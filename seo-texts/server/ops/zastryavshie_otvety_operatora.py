# -*- coding: utf-8 -*-
"""Ответы, которые оператор написал в карточке лида, но они не ушли: kind='reply', review OPERATOR,
по статусам; список не отправленных (pending и прочие не sent). Только чтение."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
сч = Counter(); висят = []
for i, st, em, кр, п, мб in c.execute("SELECT id, status, email, substr(created_at,1,16), COALESCE(panel_json,''), "
                                      "json_extract(panel_json,'$.mailbox_id') FROM confirm_reviews WHERE kind='reply' AND panel_json LIKE '%OPERATOR%'"):
    сч[st] += 1
    if st != "sent": висят.append((i, st, em, кр, мб))
print("ответы оператора из карточки лида по статусам:", dict(сч))
for x in sorted(висят, key=lambda x: x[3]): print("  ", x)
кто = Counter(); задержки = []
for кб, кр, рш in c.execute("SELECT COALESCE(decided_by,''), created_at, decided_at FROM confirm_reviews WHERE kind='reply' AND panel_json LIKE '%OPERATOR%' AND status='sent'"):
    кто[кб[:40]] += 1
    try:
        from datetime import datetime
        задержки.append((datetime.fromisoformat(рш[:26]) - datetime.fromisoformat(кр[:26])).total_seconds() / 60)
    except Exception: pass
print("кто подтвердил:", кто.most_common(8))
задержки.sort(); n = len(задержки)
if n: print("минут от создания до отправки: медиана %.1f, 90%% %.0f, макс %.0f" % (задержки[n//2], задержки[int(n*.9)], задержки[-1]))
