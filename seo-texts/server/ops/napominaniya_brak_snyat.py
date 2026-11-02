# -*- coding: utf-8 -*-
"""Снять pending-карточки напоминаний v2 с браком: адрес отдела кадров
(personal@, hr@, kadr…) и кривые обороты модели («обращение удалось ли»,
«Признательна буду»). Только карточки из _ops/napominaniya-v2.jsonl.
    napominaniya_brak_snyat.py [--primenit]"""
import io, json, re, sqlite3, sys
from datetime import datetime
АДР = re.compile(r"^(personal|personnel|hr|kadr|otdelkadrov|ok|buh|job|rezume|resume|vakans)", re.I)
ТЕКСТ = re.compile(r"обращение удалось ли|письмо удалось ли|признательн\w* буду|благодарн\w* буду", re.I)
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-v2.jsonl", encoding="utf-8")]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
n = 0
for x in з:
    if not x.get("karta"):
        continue
    ст = c.execute("SELECT status FROM confirm_reviews WHERE id=?", (x["karta"],)).fetchone()
    if not ст or ст[0] != "pending":
        continue
    п = "адрес кадров" if АДР.match(x["email"].split("@")[0]) else ("кривой оборот" if ТЕКСТ.search(x["telo"]) else "")
    if not п:
        continue
    print(x["karta"], x["email"], п)
    if "--primenit" in sys.argv:
        with c:
            n += c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'",
                           ("напоминание v2: " + п, т, т, x["karta"])).rowcount
print("снято:", n if "--primenit" in sys.argv else "СУХОЙ ПРОГОН")
