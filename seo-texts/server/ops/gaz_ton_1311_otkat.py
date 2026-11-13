# -*- coding: utf-8 -*-
"""Откат gaz_ton_1311 (владелец 13.11: «старые по старому, новые по новому»): карточкам кампании 22 вернуть body из
журнала gaz-ton-1311.jsonl (если текст ещё тот, что поставили); в messages.body_rendered вернуть абзац «Увидел, что…»
и следующий за ним (компрессоры) из старого текста карточки. Неотправленные только.   gaz_ton_1311_otkat.py [--primenit]"""
import io, json, sqlite3, sys
from collections import Counter
ПРИМ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
сч = Counter()
for с in io.open(r"C:\sender\_ops\gaz-ton-1311.jsonl", encoding="utf-8"):
    з = json.loads(с)
    р = c.execute("SELECT body FROM confirm_reviews WHERE id=?", (з["karta"],)).fetchone()
    if р and р[0] == з["stalo"]:
        сч["карточка"] += 1
        if ПРИМ: c.execute("UPDATE confirm_reviews SET body=?, edited_body=CASE WHEN edited_body IS NULL THEN NULL ELSE ? END WHERE id=?", (з["bylo"], з["bylo"], з["karta"]))
    else: сч["карточка уже не та"] += 1
    м = c.execute("SELECT status, body_rendered FROM messages WHERE id=?", (з["mid"],)).fetchone() if з.get("mid") else None
    if not м or м[0] not in ("pending_review", "scheduled", "paused") or "Увидел, что" not in (м[1] or ""): сч["письмо: пропуск"] += 1; continue
    ст = з["bylo"].split("\n\n"); нов = з["stalo"].split("\n\n")
    i = next(k for k, a in enumerate(нов) if a.startswith("Увидел, что"))
    ам = м[1].split("\n\n"); j = next((k for k, a in enumerate(ам) if a.startswith("Увидел, что")), None)
    if j is None or j + 1 >= len(ам): сч["письмо: не разобрал"] += 1; continue
    ам[j], ам[j + 1] = ст[i], ст[i + 1]
    сч["письмо"] += 1
    if ПРИМ: c.execute("UPDATE messages SET body_rendered=? WHERE id=?", ("\n\n".join(ам), з["mid"]))
if ПРИМ: c.commit()
print("ПРИМЕНЕНО" if ПРИМ else "сухой", dict(сч))
