# -*- coding: utf-8 -*-
r"""Сколько писем на Mail.ru уходит С КАЖДОГО нашего домена в день."""
import json, sqlite3
МЕЙЛРУ = ('mail.ru','bk.ru','list.ru','inbox.ru','internet.ru')
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
по = {}
for r in c.execute("""select e.mailbox_id mb, substr(e.event_ts,1,10) д, r.email
                        from events e join recipients r on r.id=e.recipient_id
                       where e.event_type='sent' and e.event_ts>='2026-08-18'"""):
    дом = str(r['email']).rsplit('@', 1)[-1].lower()
    if дом not in МЕЙЛРУ:
        continue
    наш = str(r['mb'] or '').rsplit('@', 1)[-1].lower() or '(нет)'
    по.setdefault(наш, {}).setdefault(r['д'], 0)
    по[наш][r['д']] += 1
c.close()
свод = {д: dict(sorted(v.items())) for д, v in
        sorted(по.items(), key=lambda x: -sum(x[1].values()))}
print(json.dumps({'на_mail_ru_по_нашим_доменам_и_дням': свод,
                  'доменов': len(свод)}, ensure_ascii=False, indent=1)[:2500])
