# -*- coding: utf-8 -*-
"""Проверка перекладки с пауз: в каждом переложенном письме «Меня зовут <имя>» совпадает с from_name нового ящика
(и в карточке, и в body_rendered). Только чтение."""
import json, re, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config
ящ = {m.mailbox_id: m for m in Config.load(r"C:\sender\sender.yaml").mailboxes()}
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
сч = Counter(); плохие = []
for кид, pj, body, ed, mid in c.execute("SELECT id, panel_json, body, edited_body, message_id FROM confirm_reviews WHERE panel_json LIKE '%pereлozheno_s%'"):
    д = json.loads(pj or "{}"); mb = д.get("mailbox_id")
    m = c.execute("SELECT status, mailbox_id, body_rendered FROM messages WHERE id=?", (mid,)).fetchone()
    if not m: continue
    имя = (ящ[m[1]].from_name or "").split(",")[0].split()[0] if m[1] in ящ else "?"
    for где, т in (("карточка", ed or body), ("письмо", m[2])):
        н = re.search(r"Меня зовут (\S+)", т or "")
        к = "нет «Меня зовут»" if not н else ("совпадает" if н.group(1).strip(",.") == имя else "ЧУЖОЕ ИМЯ")
        сч["%s: %s" % (где, к)] += 1
        if к == "ЧУЖОЕ ИМЯ": плохие.append((mid, m[0], где, н.group(1), имя))
    сч["статус " + m[0]] += 1
print(dict(сч)); print("чужое имя:", плохие[:15])
