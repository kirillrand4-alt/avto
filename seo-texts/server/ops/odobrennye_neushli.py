# -*- coding: utf-8 -*-
"""Одобренные карточки, чьи письма НЕ ушли (failed/skipped/застряли в sending),
за N дней по времени решения. Только чтение.  odobrennye_neushli.py [дней=7]"""
import io
import os
import sqlite3
import sys
from collections import Counter

import requests

N = int(sys.argv[1]) if len(sys.argv) > 1 else 7
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
ряды = c.execute(
    "SELECT cr.id, cr.kind, cr.status, cr.reason, substr(cr.decided_at,1,16), m.id, m.status, m.campaign_id, "
    "substr(m.updated_at,1,16), coalesce(m.last_error,''), lower(cr.email) "
    "FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    "WHERE cr.status IN ('approved','edited','sent') AND cr.decided_at >= datetime('now', ?) "
    "AND m.status IN ('failed','skipped','sending','bounced')", ("-%d days" % N,)).fetchall()
вых = ["одобренных карточек с неушедшим письмом за %d дн.: %d" % (N, len(ряды))]
вых.append("по статусу письма: %s" % dict(Counter(r[6] for r in ряды)))
пр = Counter()
for r in ряды:
    е = r[9]
    е = е.split("(")[0] if е.startswith("auto_send:уже писали") else е
    пр[(r[6], е[:80])] += 1
вых.append("причины:")
for (ст, е), n in пр.most_common(25):
    вых.append("  %5d  %-8s %s" % (n, ст, е))
вых.append("по кампаниям: %s" % dict(Counter(кам.get(r[7]) for r in ряды)))
вых.append("по дню решения: %s" % dict(sorted(Counter(r[4][:10] for r in ряды).items())))
вых.append("\nпримеры:")
for r in ряды[:15]:
    вых.append("  карточка %s (%s, %s) письмо %s %s | %s | %s" % (r[0], r[2], r[3], r[5], r[6], r[10], r[9][:90]))
# «уже писали»: прошли бы по нынешним правилам (владелец 23.10: другой адрес
# компании — через 3 дня, тот же адрес — через 30, если компания не отвечала)?
from datetime import datetime, timedelta  # noqa: E402
сейчас = datetime.utcnow()
отв = {r[0] for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                "WHERE e.event_type IN ('reply','complaint') AND r.inn IS NOT NULL")}
итог = Counter()
по_камп = Counter()
for r in ряды:
    if not r[9].startswith("auto_send:уже писали"):
        continue
    инн, em = c.execute("SELECT r.inn, lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.id=?", (r[5],)).fetchone()
    тот = c.execute("SELECT MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                    "WHERE lower(r.email)=? AND m.status='sent'", (em,)).fetchone()[0]
    комп = c.execute("SELECT MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                     "WHERE r.inn=? AND m.status='sent'", (инн,)).fetchone()[0] if инн else None
    if инн in отв:
        к = "компания отвечала — не слать"
    elif тот and сейчас - datetime.fromisoformat(тот[:19]) < timedelta(days=30):
        к = "тот же адрес моложе 30 дней"
    elif комп and сейчас - datetime.fromisoformat(комп[:19]) < timedelta(days=3):
        к = "компании писали меньше 3 дней назад"
    else:
        к = "ПРОШЛО БЫ СЕЙЧАС"
    итог[к] += 1
    if к == "ПРОШЛО БЫ СЕЙЧАС":
        по_камп[кам.get(r[7])] += 1
        вых.append("  годно: письмо %s %s" % (r[5], em)) if "--spisok" in sys.argv else None
вых.append("\n«уже писали» по нынешним правилам: %s" % dict(итог))
вых.append("прошли бы сейчас, по кампаниям: %s" % dict(по_камп))
т = "\n".join(вых)
print(т)
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/odobrennye-neushli.txt",
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
