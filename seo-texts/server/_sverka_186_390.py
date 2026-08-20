# -*- coding: utf-8 -*-
r"""186 против 390: чем меряет каждый счётчик."""
import json, sqlite3, datetime
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['сейчас_utc'] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')
# 1. событиями (так считает «Динамика 7 дней»)
итог['события_sent_по_суткам_utc'] = [dict(r) for r in c.execute(
    "select substr(event_ts,1,10) д, count(*) n from events "
    "where event_type='sent' group by 1 order by 1 desc limit 4")]
# 2. журналом отправки
итог['send_log_по_суткам_utc'] = [dict(r) for r in c.execute(
    "select substr(ts,1,10) д, count(*) n from send_log "
    'group by 1 order by 1 desc limit 4')]
итог['send_log_по_суткам_мск'] = [dict(r) for r in c.execute(
    "select substr(datetime(ts,'+3 hours'),1,10) д, count(*) n from send_log "
    'group by 1 order by 1 desc limit 4')]
# 3. счётчики ящиков (так считает «Ёмкость пулов»)
итог['ящики'] = [dict(r) for r in c.execute(
    'select mailbox_id, day_key, sent_today, daily_limit, '
    'substr(coalesce(last_sent_at,""),1,16) последняя '
    'from mailbox_state order by sent_today desc limit 12')]
итог['сумма_sent_today'] = c.execute(
    'select sum(sent_today) from mailbox_state').fetchone()[0]
итог['day_key_разные'] = dict(c.execute(
    'select day_key, count(*) from mailbox_state group by day_key').fetchall())
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
