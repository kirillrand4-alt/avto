# -*- coding: utf-8 -*-
r"""Только два ответа: тело ответа с цитатой или без, и происхождение телефона."""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS

ИНН = '7719414324'
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
лид = dict(s.execute('select * from leads where inn=? order by id desc limit 1',
                     (ИНН,)).fetchone())
тела = []
for r in s.execute("select event_type, coalesce(detail_json,'') dj from events "
                   'where recipient_id=? order by id', (лид['recipient_id'],)):
    try:
        det = json.loads(r['dj'] or '{}')
    except Exception:  # noqa: BLE001
        det = {}
    тело = ''
    for k in ('body', 'text', 'body_text', 'telo'):
        if isinstance(det.get(k), str) and det[k].strip():
            тело = det[k]
            break
    if not тело and isinstance(det.get('letter'), dict):
        тело = det['letter'].get('body') or ''
    тела.append((r['event_type'], det, тело))
s.close()

вывод = {'событий': len(тела), 'разбор': []}
for тип, det, тело in тела:
    ч = LS.bez_citaty(тело)
    вывод['разбор'].append({
        'событие': тип, 'ключи': sorted(det.keys())[:10], 'знаков': len(тело),
        'строк_с_>': sum(1 for x in тело.splitlines() if x.lstrip().startswith('>')),
        'менеджер_в_тексте': [x for x in ('Кузьмин', 'Цейзер', 'Ляпин') if x in тело],
        'менеджер_после_чистки': [x for x in ('Кузьмин', 'Цейзер', 'Ляпин') if x in ч],
        'хвост': тело.strip()[-240:],
    })
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
вывод['phone_contacts'] = [dict(r) for r in e.execute(
    'select * from phone_contacts where inn=?', (ИНН,))]
ряд = e.execute("select coalesce(phones,'') p, coalesce(director,'') d, "
                "coalesce(activity,'') a, coalesce(verified_url,'') vu "
                'from companies where inn=?', (ИНН,)).fetchone()
вывод['companies'] = dict(ряд) if ряд else {}
e.close()
print(json.dumps(вывод, ensure_ascii=False, indent=1)[:4500])
