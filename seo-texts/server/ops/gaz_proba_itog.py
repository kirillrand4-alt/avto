# -*- coding: utf-8 -*-
"""Итог пробы по адресам pending-карточек кампании 22: вердикт addr_probe, почтовик, причины «неясно». Только чтение."""
import re, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
адр = [r[0].lower() for r in c.execute("SELECT email FROM confirm_reviews WHERE campaign_id=22 AND status='pending'")]
вер = {}
for em, v, ans in c.execute("SELECT lower(email), verdict, COALESCE(answer,'') FROM addr_probe"):
    вер[em] = (v, ans)
сч = Counter(); неясно = Counter(); по_домену = Counter()
ПУБЛ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru"}
for a in адр:
    v, ans = вер.get(a, ("нет пробы", ""))
    сч[v] += 1
    if v == "неясно": неясно[re.sub(r"\d+", "#", ans)[:60]] += 1
    if v == "принимает всё": по_домену["публичный" if a.split("@")[-1] in ПУБЛ else "корпоративный"] += 1
print("адресов в очереди:", len(адр)); print("вердикты:", dict(сч.most_common()))
print("«принимает всё»:", dict(по_домену))
print("«неясно» — причины:", неясно.most_common(8))
