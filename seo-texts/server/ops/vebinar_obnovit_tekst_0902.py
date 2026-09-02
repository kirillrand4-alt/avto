# -*- coding: utf-8 -*-
"""Обновить тексты писем кампании 12 новой концовкой.

Письма уже одобрены, поэтому правим оба места: решение оператора
(confirm_reviews.body) и готовый текст письма (messages.body_rendered).
Темы не трогаем. argv: проба | делать
"""
import datetime as dt
import io
import json
import os
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
БАЗА = os.path.dirname(os.path.abspath(__file__))
письма = []
for i in range(3):
    письма.extend(json.loads(io.open(
        os.path.join(БАЗА, "vebinar_pisma_%d.json" % i), encoding="utf-8").read()))
по_почте = {п["email"]: п for п in письма}
print("новых текстов: %d" % len(по_почте))

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = list(c.execute("SELECT id, message_id, email, body FROM confirm_reviews"
                      " WHERE campaign_id=12"))
print("писем в кампании: %d" % len(ряды))

менять, нет_текста, совпало = [], 0, 0
for р in ряды:
    н = по_почте.get(р["email"])
    if н is None:
        нет_текста += 1
        continue
    if (н["тело"] or "").strip() == (р["body"] or "").strip():
        совпало += 1
        continue
    менять.append((р["id"], р["message_id"], н["тело"]))
print("к обновлению %d, уже совпадает %d, без нового текста %d"
      % (len(менять), совпало, нет_текста))

if not ДЕЛАТЬ:
    if менять:
        _, _, т = менять[0]
        print("\nпример новой концовки:\n  %s" % т.strip().split("\n\n")[-2])
    print("\nничего не изменено (режим пробы)")
    raise SystemExit(0)

сейчас = dt.datetime.now().isoformat()
о1 = о2 = 0
for рид, мид, тело in менять:
    c.execute("UPDATE confirm_reviews SET body=?, updated_at=? WHERE id=?",
              (тело, сейчас, рид))
    о1 += 1
    if мид:
        cur = c.execute("UPDATE messages SET body_rendered=?, updated_at=?"
                        " WHERE id=? AND status NOT IN ('sent','skipped','failed')",
                        (тело, сейчас, мид))
        о2 += cur.rowcount
c.commit()
print("обновлено решений %d, писем %d" % (о1, о2))

print("\n=== ПРОВЕРКА ===")
плохо = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND body_rendered LIKE '%Готова %'").fetchone()[0]
print("  писем с женской формой «Готова» в исходнике: %d (должно быть 0)" % плохо)
n = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
              " AND body_rendered LIKE '%посторонними включениями%'"
              " OR body_rendered LIKE '%посторонние включения%'").fetchone()[0]
print("  писем с новой концовкой: %d" % n)
разных = c.execute("SELECT COUNT(*) FROM (SELECT body_rendered FROM messages"
                   " WHERE campaign_id=12 GROUP BY body_rendered)").fetchone()[0]
print("  уникальных тел: %d из 175" % разных)
for x in c.execute("SELECT status, COUNT(*) n FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %s: %d" % (x["status"], x["n"]))
