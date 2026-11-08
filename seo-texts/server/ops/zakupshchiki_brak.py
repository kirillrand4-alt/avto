# -*- coding: utf-8 -*-
"""Брак среди писем закупщикам КЦ: пустая фраза про «специализированные строительные работы /
технологическое оборудование», чужие ящики (anti-corruption, hr, info-магазины) — статус карточки
и сообщения. --snyat: снять (карточку skipped, сообщение skipped, если ещё не ушло)."""
import collections, io, json, re, sqlite3, sys
from datetime import datetime, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
ПУСТО = re.compile(r"специализированн\w* строительн|вспомогательн\w* (технологическ|оборудован)|и технологическ\w* оборудовани\w*$", re.I)
ЧУЖОЙ = re.compile(r"^(anti-?corruption|hr|kadr|otdel\.?kadrov|rezume|job|press|pr|smi|reklama|marketing|dealer|sale|sales|shop|zakaz|order)\b", re.I)
брак = []
for с in io.open(r"C:\sender\_ops\zakupshchiki-kc.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x.get("otsev"): continue
    ф = x["telo"].split("\n\n")[1].split(". ")[0]
    п = "пустая фраза" if ПУСТО.search(ф) else ("чужой ящик" if ЧУЖОЙ.search(x["email"].split("@")[0]) else "")
    if п: брак.append((x["karta"], x["email"], п, ф[:110]))
сч = collections.Counter()
for k, em, п, ф in брак:
    r = c.execute("SELECT cr.status, m.status FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.id=?", (k,)).fetchone()
    сч[(п, r[0], r[1])] += 1
for к, v in сч.most_common(): print(к, v)
for b in брак[:6]: print("  ", b)
if "--snyat" in sys.argv:
    т = datetime.now(timezone.utc).isoformat(); n = 0
    with c:
        for k, em, п, ф in брак:
            m = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?", (k,)).fetchone()[0]
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status IN ('pending','approved')", ("брак закупщикам: " + п, т, т, k))
            n += c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('pending_review','scheduled')", ("брак: " + п, т, m)).rowcount
    print("снято сообщений:", n)
