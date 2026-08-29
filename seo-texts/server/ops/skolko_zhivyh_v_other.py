# -*- coding: utf-8 -*-
"""Сколько среди событий 'other' настоящих писем от людей.

'other' — это «входящее вне переписки»: ни отбивка, ни жалоба, ни ответ.
Ответом письмо считается по заголовкам In-Reply-To/References; человек,
написавший НОВОЕ письмо («компрессор КИП.»), под это правило не подходит —
и его письмо не заводит ни лид, ни отметку об ответе.
"""
import json
import re
import sqlite3
from collections import Counter
БАЗА = r"C:\sender\sender.db"
МАШИННЫЕ = ("noreply", "no-reply", "postmaster", "mailer-daemon", "mailer_daemon",
            "donotreply", "do-not-reply", "abuse@", "dmarc", "bounce@",
            "notification", "notify@", "support@google")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
итог = Counter()
живые = []
for r in c.execute("SELECT id, event_ts, mailbox_id, recipient_id, detail_json "
                   "  FROM events WHERE event_type='other' ORDER BY id"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        итог["без разбора"] += 1
        continue
    h = d.get("headers") or {}
    от = str(h.get("From") or "").lower()
    тема = str(h.get("Subject") or "")
    т = str(d.get("snippet") or "")
    доля = sum(1 for x in т[:300] if x.isprintable()) / max(1, len(т[:300]))
    if not т:
        итог["пустое тело"] += 1
    elif доля < 0.85:
        итог["двоичный мусор (вложение)"] += 1
    elif "aggregate dmarc" in т.lower() or тема.lower().startswith("report domain"):
        итог["отчёт DMARC"] += 1
    elif any(м in от for м in МАШИННЫЕ):
        итог["машинный отправитель"] += 1
    elif re.search(r"[а-яА-Я]{12}", т):
        итог["ПИСЬМО ОТ ЧЕЛОВЕКА"] += 1
        живые.append((str(r["event_ts"])[:10], r["recipient_id"],
                      str(h.get("From") or "")[:44], тема[:34],
                      " ".join(т.split())[:70]))
    else:
        итог["прочее"] += 1
for э in живые[-30:]:
    print("   %s rid=%-6s %-44s %-34s %s" % э)
print()
print("=== СОБЫТИЯ 'ДРУГОЕ' ПО СУТИ ===")
for к, v in итог.most_common():
    print("   %-28s %d" % (к, v))
привязаны = sum(1 for _, rid, _, _, _ in живые if rid)
print("\nписем от людей: %d, из них привязаны к компании: %d, висят без карточки: %d"
      % (len(живые), привязаны, len(живые) - привязаны))
c.close()
