# -*- coding: utf-8 -*-
"""Письма в расписании, где «Меня зовут <имя>» не совпадает с from_name ящика, которым уйдёт письмо: заменить имя
(карточка body/edited_body и messages.body_rendered). После двойной перекладки с пауз (13.11 и 16.11).
    imya_po_yashchiku.py [--primenit]"""
import re, sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
ящ = {m.mailbox_id: m for m in Config.load(r"C:\sender\sender.yaml").mailboxes()}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
ПР = "--primenit" in sys.argv; n = 0
for mid, mb, br in c.execute("SELECT id, mailbox_id, body_rendered FROM messages WHERE status='scheduled'").fetchall():
    if mb not in ящ or not br: continue
    имя = (ящ[mb].from_name or "").split(",")[0].split()[0]
    н = re.search(r"Меня зовут ([А-ЯЁ][а-яё]+)", br)
    if not имя or not н or н.group(1) == имя: continue
    n += 1; print(mid, mb, н.group(1), "->", имя)
    if not ПР: continue
    з = lambda т: re.sub(r"Меня зовут %s\b" % н.group(1), "Меня зовут %s" % имя, т, count=1) if т else т
    c.execute("UPDATE messages SET body_rendered=? WHERE id=? AND status='scheduled'", (з(br), mid))
    for кид, b, e in c.execute("SELECT id, body, edited_body FROM confirm_reviews WHERE message_id=?", (mid,)).fetchall():
        c.execute("UPDATE confirm_reviews SET body=?, edited_body=? WHERE id=?", (з(b), з(e), кид))
if ПР: c.commit()
print("ПРИМЕНЕНО" if ПР else "сухой", n)
