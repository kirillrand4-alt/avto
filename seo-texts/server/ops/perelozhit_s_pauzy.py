# -*- coding: utf-8 -*-
"""Переложить письма в расписании с ящиков на паузе на рабочие ящики того же направления (по кругу): messages.mailbox_id,
panel_json.mailbox_id карточки, имя менеджера во фразе «Меня зовут …» (по from_name нового ящика). 13.11: такие письма
стоят в голове очереди и обрывают проход автоотправки по КЦ.   perelozhit_s_pauzy.py [--primenit]"""
import itertools, json, re, sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
пауз = {r[0] for r in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
ящ = {m.mailbox_id: m for m in cfg.mailboxes()}
раб = {н: itertools.cycle(sorted(mb for mb, m in ящ.items() if m.division == н and mb not in пауз)) for н in ("kc", "meyer")}
имя = lambda mb: (ящ[mb].from_name or "").split(",")[0].split()[0] if ящ.get(mb) and ящ[mb].from_name else ""
сч = {"переложено": 0, "имя заменено": 0, "нет имени": 0}
for mid, mb in c.execute("SELECT id, mailbox_id FROM messages WHERE status='scheduled'").fetchall():
    if mb not in пауз or mb not in ящ: continue
    нов = next(раб[ящ[mb].division]); ст_имя, нов_имя = имя(mb), имя(нов)
    сч["переложено"] += 1
    if "--primenit" not in sys.argv: continue
    c.execute("UPDATE messages SET mailbox_id=? WHERE id=? AND status='scheduled'", (нов, mid))
    for кид, body, ed, pj in c.execute("SELECT id, body, edited_body, panel_json FROM confirm_reviews WHERE message_id=?", (mid,)).fetchall():
        д = json.loads(pj or "{}"); д["mailbox_id"] = нов; д["pereлozheno_s"] = mb
        зам = lambda t: re.sub(r"Меня зовут %s\b" % re.escape(ст_имя), "Меня зовут %s" % нов_имя, t or "", count=1) if ст_имя and нов_имя and t else t
        нб, не = зам(body), (зам(ed) if ed else ed)
        сч["имя заменено" if нб != body else "нет имени"] += 1
        c.execute("UPDATE confirm_reviews SET body=?, edited_body=?, panel_json=? WHERE id=?", (нб, не, json.dumps(д, ensure_ascii=False), кид))
    br = c.execute("SELECT body_rendered FROM messages WHERE id=?", (mid,)).fetchone()[0]
    if br and ст_имя and нов_имя: c.execute("UPDATE messages SET body_rendered=? WHERE id=?", (re.sub(r"Меня зовут %s\b" % re.escape(ст_имя), "Меня зовут %s" % нов_имя, br, count=1), mid))
if "--primenit" in sys.argv: c.commit()
print("ПРИМЕНЕНО" if "--primenit" in sys.argv else "сухой", сч, "| пауза:", sorted(пауз))
