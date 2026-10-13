# -*- coding: utf-8 -*-
"""Поставить имя в приветствие уже написанных писем (без LLM).

Владелец 13.10: «да, замени» — 45 неотправленных писем кампании 14, где имя
известно и подтверждено ящиком, но из-за ошибки (адрес не доходил до сверки)
модель поздоровалась безлично. Меняем ТОЛЬКО первую строку «Добрый день!» на
«Добрый день, <как звать>!» — форма обращения тем же кодом генератора
(_forma_obrashcheniya), те же условия (полное имя, имя ↔ ящик, ящик не общий).
Старые тексты — в _ops/privetstvie-po-imeni.jsonl (fsync) для отката.

    privetstvie_po_imeni.py            — сухой прогон
    privetstvie_po_imeni.py --primenit
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender import ai_letter as al  # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
ЖУРНАЛ = r"C:\sender\_ops\privetstvie-po-imeni.jsonl"
БЕЗЛИЧНО = re.compile(r"^(\s*)Добрый день!")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
правки, примеры = [], []
for р in c.execute("SELECT m.id, m.status, m.body_rendered, r.contact_name, r.extra_json, lower(r.email) e "
                   "FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.campaign_id=14 AND m.status IN ('scheduled','pending_review')"):
    кн = (р["contact_name"] or "").strip()
    try:
        роль = str((json.loads(р["extra_json"] or "{}") or {}).get("role") or "").strip().lower()
    except Exception:  # noqa: BLE001
        роль = ""
    if not (кн and al._polnoe_imya(кн) and al._imya_soglasuetsya_s_yashchikom(кн, р["e"])
            and роль not in ("приёмная", "общий", "бухгалтерия")):
        continue
    зовут = al._forma_obrashcheniya(кн)
    if not зовут:
        continue
    поля = []
    if р["body_rendered"] and БЕЗЛИЧНО.match(р["body_rendered"]):
        поля.append(("messages", "body_rendered", р["id"], р["body_rendered"]))
    for cr in c.execute("SELECT id, body, edited_body FROM confirm_reviews WHERE message_id=?", (р["id"],)):
        for кол in ("body", "edited_body"):
            if cr[кол] and БЕЗЛИЧНО.match(cr[кол]):
                поля.append(("confirm_reviews", кол, cr["id"], cr[кол]))
    if not поля:
        continue
    правки.append((р["id"], р["status"], зовут, поля))
    if len(примеры) < 4:
        примеры.append("m%s %s | %s <%s> → «Добрый день, %s!»" % (р["id"], р["status"], кн, р["e"], зовут))
print("писем к замене: %d (scheduled %d, pending_review %d), полей %d" % (
    len(правки), sum(1 for x in правки if x[1] == "scheduled"),
    sum(1 for x in правки if x[1] == "pending_review"), sum(len(x[3]) for x in правки)))
for п in примеры:
    print("   " + п)
if ПРИМЕНИТЬ and правки:
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        for mid, ст, зовут, поля in правки:
            ж.write(json.dumps({"ts": int(time.time()), "message_id": mid, "зовут": зовут,
                                "было": [(т, к, i, текст) for т, к, i, текст in поля]},
                               ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    with c:
        for mid, ст, зовут, поля in правки:
            for т, к, i, текст in поля:
                c.execute("UPDATE %s SET %s=? WHERE id=?" % (т, к),
                          (БЕЗЛИЧНО.sub(r"\1Добрый день, %s!" % зовут, текст, count=1), i))
    print("=== ПРИВЕТСТВИЕ: ПРИМЕНЕНО ===")
else:
    print("=== ПРИВЕТСТВИЕ: СУХОЙ ПРОГОН ===")
