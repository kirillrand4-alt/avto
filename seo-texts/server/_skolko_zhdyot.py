# -*- coding: utf-8 -*-
r"""Сколько писем реально ждёт и когда откроется окно отправки."""
import json, sqlite3, time, datetime
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['по_статусам'] = dict(c.execute(
    'select status, count(*) from confirm_reviews group by status').fetchall())
проба = {}
for e, v in c.execute('select lower(email), verdict from addr_probe'):
    проба[e] = v
свод = {}
for r in c.execute("select email from confirm_reviews where status in ('pending','edited')"):
    в = проба.get(str(r['email']).lower()) or 'вердикта нет'
    свод[в] = свод.get(в, 0) + 1
итог['ждут_всего'] = sum(свод.values())
итог['ждут_по_вердикту'] = свод
итог['окно'] = c.execute(
    "select value from panel_settings where key='sending_window'").fetchone()[0]
итог['авто'] = c.execute(
    "select value from panel_settings where key='auto_send_enabled'").fetchone()[0]
c.close()
итог['сейчас_utc'] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M (%a)')
итог['сейчас_мск'] = (datetime.datetime.utcnow() +
                      datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M (%a)')
print(json.dumps(итог, ensure_ascii=False, indent=1))
