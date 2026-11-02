# -*- coding: utf-8 -*-
"""A/B 02.11: заходы, упёршиеся в снятую карточку v2 на том же треде, кладём в
эту карточку (текст уже сгенерирован и лежит в журнале). [--primenit]"""
import io, json, sqlite3, sys
from datetime import datetime, timezone
ПРИМ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
т = datetime.now(timezone.utc).isoformat()
сделано, образцы = 0, []
for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8"):
    з = json.loads(s)
    if not з.get("karta") or not з.get("telo"):
        continue
    р = c.execute("SELECT panel_json FROM confirm_reviews WHERE id=? AND status='skipped' AND reason='напоминание v2: версия заходов (A/B 02.11)'", (з["karta"],)).fetchone()
    if not р:
        continue
    п = json.loads(р[0] or "{}")
    п["napominanie"] = з.get("zahod")
    п["vruchnuyu"] = "напоминания A/B 02.11: заходы"
    сделано += 1
    if len(образцы) < 4:
        образцы.append((з.get("zahod"), з["email"], з["telo"]))
    if ПРИМ:
        with c:
            c.execute("UPDATE confirm_reviews SET subject=?, body=?, edited_body=NULL, panel_json=?, status='pending', reason=NULL, decided_at=NULL, updated_at=? WHERE id=? AND status='skipped'",
                      (з["tema"], з["telo"], json.dumps(п, ensure_ascii=False), т, з["karta"]))
print("заходов в карточки:", сделано, "(применено)" if ПРИМ else "(СУХОЙ ПРОГОН)")
for зх, e, тело in образцы:
    print("\n--- заход %s → %s\n%s" % (зх, e, тело))
