# -*- coding: utf-8 -*-
r"""Сколько писем ушло НА адреса Mail.ru и с каких наших доменов."""
import json, sqlite3
МЕЙЛРУ = ('mail.ru','bk.ru','list.ru','inbox.ru','internet.ru','mail.ua')
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
всего = получатели_мейлру = 0
по_домену = {}
по_дням = {}
кол = [x[1] for x in c.execute('pragma table_info(send_log)')]
итог['столбцы_send_log'] = кол
поле = next((k for k in ('mailbox_id','mailbox','from_email','sender','box') if k in кол), None)
sql = ('select email, coalesce("%s",\'\') mb, ts from send_log' % поле) if поле \
      else "select email, '' mb, ts from send_log"
for r in c.execute(sql):
    всего += 1
    дом = str(r['email']).rsplit('@', 1)[-1].lower()
    if дом not in МЕЙЛРУ:
        continue
    получатели_мейлру += 1
    наш = str(r['mb']).rsplit('@', 1)[-1].lower() or '(не указан)'
    по_домену[наш] = по_домену.get(наш, 0) + 1
    по_дням[str(r['ts'])[:10]] = по_дням.get(str(r['ts'])[:10], 0) + 1
итог['отправок_всего'] = всего
итог['из_них_на_mail_ru'] = получатели_мейлру
итог['с_наших_доменов'] = dict(sorted(по_домену.items(), key=lambda x: -x[1]))
итог['по_дням'] = dict(sorted(по_дням.items())[-7:])
итог['доменов_отправки'] = len(по_домену)
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
