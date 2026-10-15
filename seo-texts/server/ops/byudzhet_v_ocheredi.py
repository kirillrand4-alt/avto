# -*- coding: utf-8 -*-
"""«Потратить/освоить бюджет» в письмах очереди -> формы владельца (15.10:
«пропиши в правилах, а готовые механически заверши»). Живые карточки
(pending/approved/edited): body и edited_body через ai_letter.bez_potratit_byudzhet,
и текст связанного письма messages.body_rendered. Резерв — _ops/byudzhet-v-ocheredi.jsonl.

    byudzhet_v_ocheredi.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _БЮДЖЕТ_RE, bez_potratit_byudzhet  # noqa: E402

ПРИМ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = [dict(р) for р in c.execute(
    "SELECT id, message_id, body, edited_body FROM confirm_reviews WHERE status IN ('pending','approved','edited') "
    "AND COALESCE(kind,'outbound')='outbound'")]
надо = [р for р in ряды if _БЮДЖЕТ_RE.search(р["body"] or "") or _БЮДЖЕТ_RE.search(р["edited_body"] or "")]
print("живых карточек: %d, с «потратить бюджет»: %d" % (len(ряды), len(надо)))
for р in надо[:2]:
    print("   #%d: %s" % (р["id"], _БЮДЖЕТ_RE.search(р["body"] or р["edited_body"]).group(0)))
if ПРИМ and надо:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with io.open(r"C:\sender\_ops\byudzhet-v-ocheredi.jsonl", "a", encoding="utf-8") as ж:
        for р in надо:
            ж.write(json.dumps(р, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    with c:
        for р in надо:
            c.execute("UPDATE confirm_reviews SET body=?, edited_body=?, updated_at=? WHERE id=?",
                      (bez_potratit_byudzhet(р["body"]), р["edited_body"] and bez_potratit_byudzhet(р["edited_body"]),
                       т, р["id"]))
            if р["message_id"]:
                м = c.execute("SELECT body_rendered FROM messages WHERE id=?", (р["message_id"],)).fetchone()
                if м and м[0] and _БЮДЖЕТ_RE.search(м[0]):
                    c.execute("UPDATE messages SET body_rendered=?, updated_at=? WHERE id=?",
                              (bez_potratit_byudzhet(м[0]), т, р["message_id"]))
    print("исправлено: %d" % len(надо))
print("=== БЮДЖЕТ В ОЧЕРЕДИ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
