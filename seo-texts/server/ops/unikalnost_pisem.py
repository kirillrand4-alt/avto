# -*- coding: utf-8 -*-
"""Насколько уникальны письма кампании: по предложениям — какая доля текста письма встречается ещё в ≥10 письмах
(шаблонная часть), сколько разных тем, сколько полностью одинаковых «скелетов» (письмо без фразы про компанию и имени).
Только чтение.   unikalnost_pisem.py <id кампании>"""
import re, sqlite3, sys
from collections import Counter
к = int(sys.argv[1])
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
р = c.execute("SELECT subject, COALESCE(edited_body, body) FROM confirm_reviews WHERE campaign_id=? AND status IN ('pending','approved')", (к,)).fetchall()
пред = lambda т: [x.strip() for x in re.split(r"(?<=[.!?])\s+", т) if x.strip()]
сч = Counter(п for _, т in р for п in set(пред(т)))
доли = []; скелеты = Counter()
for _, т in р:
    пп = пред(т); всего = sum(len(x) for x in пп)
    общ = sum(len(x) for x in пп if сч[x] >= 10)
    доли.append(общ / max(1, всего))
    скелеты[tuple(x for x in пп if сч[x] >= 10)] += 1
доли.sort()
print("писем:", len(р), "| разных тем:", len({т for т, _ in р}))
print("доля шаблонного текста в письме: медиана %.0f%%, мин %.0f%%, макс %.0f%%" % (100 * доли[len(доли) // 2], 100 * доли[0], 100 * доли[-1]))
print("разных «скелетов» (набор шаблонных фраз): %d; самый частый скелет у %d писем" % (len(скелеты), скелеты.most_common(1)[0][1]))
print("самые частые фразы:", [(п[:60], н) for п, н in сч.most_common(6)])
