# -*- coding: utf-8 -*-
"""Вердикты пробы по доменам группы mail.ru по дням (addr_probe, source='проба'): когда mail.ru перестал
отвечать «нет ящика». Только чтение."""
import sqlite3
from collections import defaultdict, Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
д = defaultdict(Counter)
for em, v, ts in c.execute("SELECT email, verdict, substr(ts,1,10) FROM addr_probe WHERE source='проба'"):
    дом = em.split("@")[-1]
    if дом in ("mail.ru", "bk.ru", "list.ru", "inbox.ru"): д[ts][v] += 1
for день in sorted(д)[-30:]: print(день, dict(д[день]))
