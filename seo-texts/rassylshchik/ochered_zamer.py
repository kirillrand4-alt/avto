# -*- coding: utf-8 -*-
"""Сколько ложных новостей стоит в ЖИВОЙ очереди и что по ним уже ушло. ТОЛЬКО ЧТЕНИЕ."""
import base64
import json
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

INN = json.load(open('/home/user/work/mismatch-inn.json'))
SCRIPT = '''# -*- coding: utf-8 -*-
import json, sqlite3
INN = %s
cx = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
cx.row_factory = sqlite3.Row
o = {}
o['poluchateli_po_segmentu'] = {r[0]: r[1] for r in cx.execute(
    'select coalesce(segment,"(нет)"), count(*) from recipients group by 1 order by 2 desc')}
o['poluchateli_po_istochniku'] = {r[0]: r[1] for r in cx.execute(
    'select coalesce(source,"(нет)"), count(*) from recipients group by 1 order by 2 desc')}
o['pisma_po_kampanii_i_statusu'] = {'%%s/%%s' %% (r[0], r[1]): r[2] for r in cx.execute(
    'select campaign_id, status, count(*) from messages group by 1,2 order by 1,2')}
q = ','.join('?' * len(INN))
o['nashi'] = []
for r in cx.execute('select id,inn,email,segment,valid_status,source from recipients '
                    'where inn in (%%s)' %% q, INN):
    d = dict(r)
    d['pisma'] = [dict(m) for m in cx.execute(
        'select id,campaign_id,status,scheduled_at,sent_at from messages where recipient_id=?',
        (r['id'],))]
    o['nashi'].append(d)
o['nashih_poluchateley'] = len(o['nashi'])
o['inn_bez_poluchatelya'] = [i for i in INN if not any(n['inn'] == i for n in o['nashi'])]
o['supressiya_kolonki'] = [d[1] for d in cx.execute('pragma table_info(suppression)')]
o['supressiya_vsego'] = cx.execute('select count(*) from suppression').fetchone()[0]
o['supressiya_obrazec'] = [dict(r) for r in cx.execute('select * from suppression limit 2')]
print(json.dumps(o, ensure_ascii=False))
''' % json.dumps(INN)

dest = r'C:\sender\ochered_zamer_3s.py'
R.submit('enrich_contacts', {'op': 'panel_file_put',
         'files': [{'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'timeout': 300}, timeout=600)
open('/home/user/work/ochered-zamer.json', 'w', encoding='utf-8').write(
    json.dumps(r, ensure_ascii=False, indent=1))
d = r.get('data') or {}
print('rc', d.get('rc'))
print((d.get('stdout_tail') or d.get('stderr_tail') or '')[:5500])
