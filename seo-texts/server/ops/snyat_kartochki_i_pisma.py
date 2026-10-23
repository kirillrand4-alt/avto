# -*- coding: utf-8 -*-
"""Снять с отправки карточки и их письма (владелец 23.10: «да, снимай» —
группа grainrus.com получала бы ~10 писем за неделю). Карточка → skipped,
письмо (scheduled / pending_review / approved) → skipped с причиной. Уже
отправленное не трогаем. Журнал _ops/snyat-kartochki.jsonl (прежние статусы).
    snyat_kartochki_i_pisma.py <id карточек через запятую> "<причина>" [--primenit]"""
import io
import json
import sqlite3
import sys
import time

ids = [int(x) for x in sys.argv[1].split(",")]
причина = sys.argv[2]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
план = []
for i in ids:
    r = c.execute("SELECT c.id, c.status, c.email, c.message_id, m.status FROM confirm_reviews c "
                  "LEFT JOIN messages m ON m.id=c.message_id WHERE c.id=?", (i,)).fetchone()
    if not r:
        print("#%d нет карточки" % i)
        continue
    if r[4] == "sent" or r[1] == "sent":
        print("#%d уже отправлено — не трогаю" % i)
        continue
    план.append(r)
    print("#%d %s | карточка %s | письмо %s %s" % (r[0], r[2], r[1], r[3], r[4]))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Снять — --primenit")
    sys.exit()
with c, io.open(r"C:\sender\_ops\snyat-kartochki.jsonl", "a", encoding="utf-8") as ж:
    for kid, kst, em, mid, mst in план:
        c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_by=?, decided_at=?, updated_at=? WHERE id=?",
                  (причина, "Claude по команде владельца", т, т, kid))
        if mid and mst in ("scheduled", "pending_review", "approved"):
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status=?",
                      (причина, т, mid, mst))
        ж.write(json.dumps({"kartochka": kid, "bylo": kst, "message": mid, "msg_bylo": mst, "ts": т}, ensure_ascii=False) + "\n")
print("СНЯТО:", len(план))
