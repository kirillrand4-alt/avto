# -*- coding: utf-8 -*-
"""Опыт «текст или домен» (владелец 15.10: «сам сможешь отправить и проверить
реальные письма?»). Один домен (compressor-pro-systems.ru, сегодня 0 отказов из 6),
два текста:
  НОВЫЙ — письма КЦ, сгенерированные после правки 15.10 (разные слова, без «КП с
          ценой»/«до конца года»): 6 шт., ящики vladislav.melnikov, i.lyapin, balakirev.a;
  СТАРЫЙ — письма прежнего шаблона из расписания: 6 шт., ящики a.dmitriev, kirchatov.n.
Ящик закрепляется за письмом (messages.mailbox_id — автоотправка не подменит),
срок — раньше всей очереди, с паузы снимаются только эти 5 ящиков. Журнал
_ops/opyt-kc.jsonl. Итог — opyt_kc.py --itog (отправлено/спам-отказ по вариантам).

    opyt_kc.py [--primenit | --itog]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

ЖУР = r"C:\sender\_ops\opyt-kc.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
if "--itog" in sys.argv:
    for с in io.open(ЖУР, encoding="utf-8"):
        з = json.loads(с)
        ev = [r[0] for r in c.execute("SELECT event_type FROM events WHERE message_id=? AND event_type IN ('sent','reject_spam','bounce')", (з["mid"],))]
        ст = c.execute("SELECT status FROM messages WHERE id=?", (з["mid"],)).fetchone()[0]
        print("%-6s %-44s %-30s %s %s" % (з["вариант"], з["ящик"], з["email"], ст, ",".join(ev)))
    print("=== ОПЫТ КЦ: ИТОГ ===")
    sys.exit(0)
НОВ_Я = ["vladislav.melnikov@compressor-pro-systems.ru", "i.lyapin@compressor-pro-systems.ru", "balakirev.a@compressor-pro-systems.ru"]
СТ_Я = ["a.dmitriev@compressor-pro-systems.ru", "kirchatov.n@compressor-pro-systems.ru"]
ШАБЛОН = re.compile(r"КП с цен|успеть до конца года")
# новые: карточки кампании 15 в ожидании, без шаблонных фраз
новые = [dict(r) for r in c.execute(
    "SELECT cr.id rid, cr.message_id mid, cr.email, cr.body FROM confirm_reviews cr WHERE cr.campaign_id=15 "
    "AND cr.status='pending' ORDER BY cr.id DESC LIMIT 40")]
новые = [r for r in новые if r["mid"] and not ШАБЛОН.search(r["body"] or "")][:6]
старые = [dict(r) for r in c.execute(
    "SELECT m.id mid, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=15 "
    "AND m.status='scheduled' ORDER BY m.id LIMIT 30")]
старые = [r for r in старые if ШАБЛОН.search((c.execute("SELECT body FROM confirm_reviews WHERE message_id=?", (r["mid"],)).fetchone() or [""])[0] or "")][:6]
print("новых писем: %d, старых: %d" % (len(новые), len(старые)))
for r in новые[:2]:
    print("--- НОВЫЙ пример:\n" + (r["body"] or "")[:900])
if "--primenit" not in sys.argv:
    print("=== ОПЫТ КЦ: сухой прогон ===")
    sys.exit(0)
мин = c.execute("SELECT min(scheduled_at) FROM messages WHERE status='scheduled'").fetchone()[0]
срок = (datetime.fromisoformat(str(мин)[:19]) - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S")
т = time.strftime("%Y-%m-%dT%H:%M:%S")
ж = io.open(ЖУР, "a", encoding="utf-8")
with c:
    for i, r in enumerate(новые):
        я = НОВ_Я[i % len(НОВ_Я)]
        c.execute("UPDATE messages SET status='scheduled', scheduled_at=?, mailbox_id=?, updated_at=? WHERE id=?", (срок, я, т, r["mid"]))
        c.execute("UPDATE confirm_reviews SET status='approved', decided_by='опыт КЦ 15.10', decided_at=?, "
                  "reason='bulk-to-auto: опыт текст/домен', updated_at=? WHERE id=?", (т, т, r["rid"]))
        ж.write(json.dumps({"вариант": "НОВЫЙ", "mid": r["mid"], "ящик": я, "email": r["email"]}, ensure_ascii=False) + "\n")
    for i, r in enumerate(старые):
        я = СТ_Я[i % len(СТ_Я)]
        c.execute("UPDATE messages SET scheduled_at=?, mailbox_id=?, updated_at=? WHERE id=?", (срок, я, т, r["mid"]))
        ж.write(json.dumps({"вариант": "СТАРЫЙ", "mid": r["mid"], "ящик": я, "email": r["email"]}, ensure_ascii=False) + "\n")
    c.execute("UPDATE mailbox_state SET paused=0, pause_reason=NULL, updated_at=? WHERE mailbox_id IN (%s)"
              % ",".join("?" * 5), [т] + НОВ_Я + СТ_Я)
ж.flush()
os.fsync(ж.fileno())
print("поставлено: новых %d, старых %d; с паузы сняты 5 ящиков compressor-pro-systems.ru" % (len(новые), len(старые)))
print("=== ОПЫТ КЦ: ЗАПУЩЕН ===")
