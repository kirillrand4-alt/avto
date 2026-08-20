# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
d = {}
d['ждут_по_ящику'] = [dict(r) for r in c.execute(
    "select coalesce(nullif(mailbox_id,''),'(нет ящика)') я, status, count(*) n "
    "from messages where sent_at is null and status in ('scheduled','sending') "
    'group by 1,2 order by 3 desc limit 12')]
d['ждут_на_сегодня'] = [dict(r) for r in c.execute(
    "select status, count(*) n from messages where sent_at is null "
    "and status in ('scheduled','sending') group by 1")]
d['планы_вперёд'] = [dict(r) for r in c.execute(
    "select substr(scheduled_at,1,10) д, count(*) n from messages "
    "where sent_at is null and status in ('scheduled','sending') "
    'group by 1 order by 1 desc limit 6')]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:1800])
