# -*- coding: utf-8 -*-
"""Нет ли в очереди (scheduled / pending_review / sending) адресов с приговором пробы.

Приговор — «нет ящика» или «нет MX» (правило CLAUDE.md). Плюс: у скольких
адресов в очереди проба ещё не прошла вовсе.
"""
import sqlite3
import sys
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ПРИГОВОР = ("нет ящика", "нет MX")
вердикт = {р[0].lower(): (р[1], р[2]) for р in c.execute("SELECT email, verdict, source FROM addr_probe")}
строки = [dict(р) for р in c.execute(
    "SELECT m.id, m.status, m.campaign_id, m.scheduled_at, lower(r.email) e, r.company_name "
    "FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status IN ('scheduled','pending_review','sending')")]
print("в очереди писем: %d; по статусам: %s" % (len(строки), dict(Counter(р["status"] for р in строки))))
по_вердикту = Counter((вердикт.get(р["e"]) or ("не проверен",))[0] for р in строки)
print("вердикты пробы у адресов очереди: %s" % dict(по_вердикту.most_common()))
мёртвые = [р for р in строки if (вердикт.get(р["e"]) or ("",))[0] in ПРИГОВОР]
print("С ПРИГОВОРОМ В ОЧЕРЕДИ: %d" % len(мёртвые))
for р in мёртвые[:15]:
    print("   m%s %s камп %s | %s <%s> | %s (%s)" % (р["id"], р["status"], р["campaign_id"],
          str(р["company_name"])[:28], р["e"], *вердикт[р["e"]]))
if "--snyat" in sys.argv and мёртвые:
    from datetime import datetime, timezone
    т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        n = c.executemany(
            "UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? "
            "AND status IN ('scheduled','pending_review')",
            [("снято 13.10: приговор пробы «%s»" % вердикт[р["e"]][0], т, р["id"]) for р in мёртвые]).rowcount
    print("снято: %d" % n)
print("=== МЁРТВЫЕ В ОЧЕРЕДИ ===")
