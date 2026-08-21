# -*- coding: utf-8 -*-
r"""Лид «Кейтеринг Технолоджи»: тело ответа, откуда телефон, что знаем о компании."""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS

ИНН = '7719414324'
d = {}
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
лид = dict(s.execute('select * from leads where inn=? order by id desc limit 1',
                     (ИНН,)).fetchone())
d['лид'] = {k: str(v)[:60] for k, v in лид.items()
            if k in ('id', 'email', 'phone', 'person', 'recipient_id')}

письма = []
for r in s.execute('select event_type, event_ts, coalesce(detail_json,\'\') dj '
                   'from events where recipient_id=? order by id',
                   (лид['recipient_id'],)):
    try:
        det = json.loads(r['dj'] or '{}')
    except Exception:  # noqa: BLE001
        det = {}
    тело = ''
    for ключ in ('body', 'text', 'body_text', 'letter', 'telo'):
        зн = det.get(ключ)
        if isinstance(зн, dict):
            зн = зн.get('body') or зн.get('text')
        if isinstance(зн, str) and зн.strip():
            тело = зн
            break
    чисто = LS.bez_citaty(тело)
    письма.append({
        'событие': r['event_type'], 'когда': str(r['event_ts'])[:16],
        'ключи_detail': sorted(det.keys())[:12],
        'знаков': len(тело),
        'строк_с_цитатой': sum(1 for x in тело.splitlines()
                               if x.lstrip().startswith('>')),
        'менеджер_в_тексте': [x for x in ('Кузьмин', 'Цейзер', 'Ляпин')
                              if x in тело],
        'менеджер_после_чистки': [x for x in ('Кузьмин', 'Цейзер', 'Ляпин')
                                  if x in чисто],
        'хвост_как_есть': тело.strip()[-300:],
    })
d['письма'] = письма
s.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
d['phone_contacts_колонки'] = [x[1] for x in e.execute(
    'PRAGMA table_info(phone_contacts)')]
d['phone_contacts_строки'] = [
    {k: (str(v)[:60] if v is not None else None) for k, v in dict(r).items()}
    for r in e.execute('select * from phone_contacts where inn=? limit 8', (ИНН,))]
таблицы = [x[0] for x in e.execute("select name from sqlite_master where type='table'")]
d['где_ещё_есть_этот_инн'] = []
for т in таблицы:
    кол = [x[1] for x in e.execute('PRAGMA table_info(%s)' % т)]
    if 'inn' not in кол:
        continue
    try:
        n = e.execute('select count(*) from %s where inn=?' % т, (ИНН,)).fetchone()[0]
    except Exception:  # noqa: BLE001
        continue
    if n:
        d['где_ещё_есть_этот_инн'].append({'таблица': т, 'строк': n,
                                           'колонки': кол[:14]})
e.close()

п = r'C:\sender\sender\api\app.py'
with open(п, encoding='utf-8') as f:
    текст = f.read()
m = re.search(r'def _kontakty_kompanii.*?(?=\ndef |\n@app|\Z)', текст, re.S)
d['_kontakty_kompanii'] = (m.group(0)[:2600] if m else 'не нашёл')
print(json.dumps(d, ensure_ascii=False, indent=1)[:6000])
