# -*- coding: utf-8 -*-
"""Письма в расписании на ящиках на паузе: кампании, срок, from_name ящика и как в тексте записано «Меня зовут …»
(чтобы при перекладке заменить имя). Только чтение."""
import re, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config
cfg = Config.load(r"C:\sender\sender.yaml"); ящ = {m.mailbox_id: m for m in cfg.mailboxes()}
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
пауз = {r[0] for r in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
рр = c.execute("SELECT m.id, m.mailbox_id, m.campaign_id, m.scheduled_at, m.body_rendered, cr.body, cr.edited_body FROM messages m "
               "LEFT JOIN confirm_reviews cr ON cr.message_id=m.id WHERE m.status='scheduled'").fetchall()
п = [р for р in рр if р[1] in пауз]
print("в расписании всего %d, на паузе %d" % (len(рр), len(п)))
print("по кампаниям:", Counter(р[2] for р in п), "| самый ранний срок на паузе:", min((р[3] for р in п), default=None),
      "| самый ранний срок у рабочих:", min((р[3] for р in рр if р[1] not in пауз and р[1]), default=None))
for mb in sorted({р[1] for р in п}):
    print(mb, "| from_name:", ящ[mb].from_name if mb in ящ else "НЕТ В КОНФИГЕ")
for р in п[:4]:
    т = р[6] or р[5] or р[4] or ""
    м = re.search(r"Меня зовут [^,.\n]{0,40}", т)
    print(р[0], р[1], "| текст:", м.group(0) if м else "нет «Меня зовут»", "| есть body_rendered:", bool(р[4]))
