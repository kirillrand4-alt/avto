# -*- coding: utf-8 -*-
r"""Что реально ждёт отправки: очередь писем и очередь подтверждений."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
d = {}
d['messages_по_статусу'] = dict(c.execute(
    "select coalesce(status,'(пусто)'), count(*) from messages group by 1 "
    'order by 2 desc').fetchall())
d['messages_не_отправлены'] = dict(c.execute(
    "select coalesce(status,'(пусто)'), count(*) from messages "
    'where sent_at is null group by 1 order by 2 desc').fetchall())
d['confirm_по_статусу'] = dict(c.execute(
    'select status, count(*) from confirm_reviews group by status').fetchall())
# запланированы на сегодня?
кол = [r[1] for r in c.execute('pragma table_info(messages)')]
d['столбцы_messages'] = кол
if 'scheduled_at' in кол:
    d['по_дате_плана'] = [dict(r) for r in c.execute(
        "select substr(scheduled_at,1,10) д, count(*) n from messages "
        'where sent_at is null group by 1 order by 1 limit 6')]
# сколько approved ещё не ушло
d['approved_без_отправки'] = c.execute("""
   select count(*) from confirm_reviews cr where cr.status='approved'
     and not exists (select 1 from messages m where m.id=cr.message_id
                       and m.sent_at is not null)""").fetchone()[0]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
