# -*- coding: utf-8 -*-
"""Отклик по дню ОТПРАВКИ письма и кампании (последние N дней): ушло / ответили люди / автоответ."""
import collections, sqlite3, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
им = dict(c.execute("SELECT id, name FROM campaigns"))
ушло = collections.Counter(); отв = collections.Counter(); авто = collections.Counter()
for mid, cid, d in c.execute("SELECT id, campaign_id, substr(sent_at,1,10) FROM messages WHERE status='sent' AND sent_at>=date('now', ?)", ("-%d days" % N,)):
    ушло[(d, cid)] += 1
for et, cid, d in c.execute("SELECT e.event_type, m.campaign_id, substr(m.sent_at,1,10) FROM events e JOIN messages m ON m.id=e.message_id "
                            "WHERE e.event_type IN ('reply','reply_auto') AND m.sent_at>=date('now', ?) GROUP BY e.message_id, e.event_type", ("-%d days" % N,)):
    (отв if et == "reply" else авто)[(d, cid)] += 1
for (d, cid), n in sorted(ушло.items()):
    if n >= 30:
        print("%s  %-32s ушло %4d  ответов %3d  %5.2f%%  автоотв %3d" % (d, им.get(cid, cid)[:32], n, отв[(d, cid)], 100.0 * отв[(d, cid)] / n, авто[(d, cid)]))
