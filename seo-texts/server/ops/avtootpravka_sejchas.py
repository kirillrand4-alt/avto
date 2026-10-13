# -*- coding: utf-8 -*-
"""Автоотправка сейчас: что одобрено, что уже должно было уйти, что ушло, что упало.

Владелец 13.10: «я отправил в автоотправку много, посмотри какие из них должны
уже отправиться и отправились ли».
"""
import sqlite3
from collections import Counter
from datetime import datetime, timezone

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
сейчас = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
print("сейчас UTC %s" % сейчас)
кол = [р[1] for р in c.execute("PRAGMA table_info(messages)")]
поле_срока = "scheduled_at" if "scheduled_at" in кол else None
строки = [dict(р) for р in c.execute(
    "SELECT m.id, m.status, m.mailbox_id, m.%s AS sch, m.sent_at, m.attempt_count, m.last_error, "
    "m.updated_at, m.campaign_id FROM messages m "
    "WHERE m.updated_at >= datetime('now','-2 days') OR m.status IN ('scheduled','sending')"
    % (поле_срока or "created_at"))] if True else []
по = Counter((р["campaign_id"], р["status"]) for р in строки)
print("сообщения за 2 дня и в работе (кампания, статус): %s" % dict(по))
срок = [р for р in строки if р["status"] in ("scheduled", "sending")]
должны = [р for р in срок if str(р["sch"] or "") <= сейчас]
print("в расписании/отправке: %d, из них срок уже наступил: %d" % (len(срок), len(должны)))
print("сроки в расписании (по часу UTC): %s" % dict(sorted(Counter(str(р['sch'])[:13] for р in срок).items())[:12]))
ушли = [р for р in строки if р["status"] == "sent" and str(р["sent_at"] or "") >= сейчас[:10]]
print("ушло сегодня: %d; по ящикам: %s" % (len(ушли), dict(Counter(р["mailbox_id"] for р in ушли))))
if ушли:
    print("   первое %s, последнее %s" % (min(р["sent_at"] for р in ушли), max(р["sent_at"] for р in ушли)))
упали = [р for р in строки if р["status"] in ("failed", "bounced") and str(р["updated_at"] or "") >= сейчас[:10]]
print("упало сегодня: %d" % len(упали))
for р in упали[:6]:
    print("   m%s %s | %s" % (р["id"], р["status"], str(р["last_error"])[:140]))
ош = Counter(str(р["last_error"] or "")[:70] for р in должны if р["last_error"])
for к, n in ош.most_common(5):
    print("   ошибка у наступивших: %d × %s" % (n, к))
print("=== АВТООТПРАВКА ===")
