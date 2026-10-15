# -*- coding: utf-8 -*-
"""Снять письма КЦ (кампания 15) старого шаблона — «КП с ценой…», «до конца года»
в теме: опыт 15.10 показал, что Яндекс режет их как спам (0 из 2 против 6 из 6
у нового текста). Письма (scheduled/approved/pending) -> skipped, карточки ->
skipped с причиной; компании вернутся в генерацию по новым правилам.
Резерв — _ops/snyat-staryy-shablon-kc.jsonl.

    snyat_staryy_shablon_kc.py [--primenit]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
ПРИМ = "--primenit" in sys.argv
ШАБЛОН = re.compile(r"(?i)КП\s+с\s+цен|успеть\s+до\s+конца\s+года")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = [dict(r) for r in c.execute(
    "SELECT cr.id rid, cr.status cst, cr.body, cr.edited_body, m.id mid, m.status mst, m.subject FROM confirm_reviews cr "
    "JOIN messages m ON m.id=cr.message_id WHERE cr.campaign_id=15 AND m.status IN ('scheduled','approved','pending_review') "
    "AND cr.status IN ('pending','approved','edited')")]
старые = [р for р in ряды if ШАБЛОН.search((р["edited_body"] or р["body"] or "")) or re.search(r"(?i)до\s+конца\s+года", р["subject"] or "")]
print("живых писем КЦ: %d, старого шаблона: %d" % (len(ряды), len(старые)))
if ПРИМ and старые:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with io.open(r"C:\sender\_ops\snyat-staryy-shablon-kc.jsonl", "a", encoding="utf-8") as ж:
        for р in старые:
            ж.write(json.dumps({k: р[k] for k in ("rid", "mid", "cst", "mst")}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    with c:
        for р in старые:
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?",
                      ("старый шаблон КЦ: спам-фильтр Яндекса (опыт 15.10), перегенерация", т, р["mid"]))
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_by='перегенерация КЦ 15.10', "
                      "decided_at=?, updated_at=? WHERE id=?", ("старый шаблон КЦ — перегенерация", т, т, р["rid"]))
    print("снято: %d" % len(старые))
print("=== СТАРЫЙ ШАБЛОН КЦ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
