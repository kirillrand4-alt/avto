# -*- coding: utf-8 -*-
"""Проверка: карточки КЦ со статусом approved — какой статус у их писем (messages). Только чтение."""
import re, sqlite3
from collections import Counter
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
кам = {i: н for i, н in к.execute("SELECT id, name FROM campaigns")}
кц = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
сч = Counter()
for кид, ст in к.execute("SELECT cr.campaign_id, COALESCE(m.status,'нет письма') FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.status='approved'"):
    if кид in кц: сч[(кам[кид], ст)] += 1
for (н, ст), n in sorted(сч.items()): print("%-26s %-14s %d" % (н, ст, n))
