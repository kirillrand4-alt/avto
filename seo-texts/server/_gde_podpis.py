# -*- coding: utf-8 -*-
r"""Где именно на странице лида стоит «С уважением»: в нашем письме или в ответе.

Подпись режем только у НАШИХ писем — своя подпись клиента часть его текста.
Грубая проверка «есть ли строка на странице» этого не различает, поэтому
смотрим по блокам: исходящие (.m.out) и входящие (.m.in) отдельно.
"""
import json
import re
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS

c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
лид = c.execute(
    "select l.id, l.email, l.company_name from leads l "
    "where l.status<>'deleted' and exists(select 1 from events e "
    "  where e.recipient_id=l.recipient_id and e.event_type like 'reply%') "
    'order by l.id desc limit 1').fetchone()
c.close()
r = LS.sozdat(int(лид['id']), kto='проба-подписи')
стр = urllib.request.urlopen(
    'http://127.0.0.1:8091/lid/%s' % r['token'], timeout=25
).read().decode('utf-8', 'replace')

блоки = re.findall(r'<div class="m (in|out)">(.*?)</div>\s*(?=<div class="m |</div>)',
                   стр, re.S)
if not блоки:
    блоки = [(m.group(1), m.group(0)) for m in
             re.finditer(r'<div class="m (in|out)">.*?(?=<div class="m |<div class="k")',
                         стр, re.S)]
итог = {'лид': лид['company_name'], 'блоков': len(блоки), 'разбор': []}
for куда, тело in блоки:
    текст = re.sub(r'<[^>]+>', ' ', тело)
    итог['разбор'].append({
        'куда': куда,
        'есть_с_уважением': bool(re.search(r'С\s+уважением', текст, re.I)),
        'знаков': len(текст),
        'хвост': текст.strip()[-120:].replace('\n', ' '),
    })
LS.otozvat(int(лид['id']))
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
