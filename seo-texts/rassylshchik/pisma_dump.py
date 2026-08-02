# -*- coding: utf-8 -*-
"""Выгрузка таблиц рассыльщика на дроп для разбора в песочнице. ТОЛЬКО ЧТЕНИЕ на сервере.

Владелец спросил про ушедшие письма: что стояло в очереди и что реально ушло — менялся ли
контакт, текст, тема; есть ли общие закономерности правок. Через `stdout_tail` этого не увидеть,
он режется на 6000 знаках. Поэтому сервер только выгружает таблицы файлом на дроп, а весь разбор
идёт здесь: правка регулярки не должна стоить серверного задания.
"""
import base64
import json
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

SCRIPT = r'''# -*- coding: utf-8 -*-
import gzip, json, os, sqlite3, urllib.request
cx = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True); cx.row_factory = sqlite3.Row
out = {}
for t in ('messages','recipients','confirm_reviews','ai_letter_log','audit_log','events',
          'send_log','campaigns','sequence_steps','suppression','leads','lead_events'):
    try:
        out[t] = [dict(r) for r in cx.execute('select * from "%s"' % t)]
    except Exception as e:
        out[t] = {'oshibka': str(e)}
b = gzip.compress(json.dumps(out, ensure_ascii=False, default=str).encode('utf-8'))
p = r'C:\sender\sender-dump-3s.json.gz'
open(p, 'wb').write(b)
U = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
T = os.environ.get('DROP_TOKEN', '')
req = urllib.request.Request(U + '/sender-dump-3s.json.gz', data=b, method='PUT',
                             headers={'X-Drop-Token': T})
try:
    r = urllib.request.urlopen(req, timeout=300).read().decode('utf-8', 'replace')
except Exception as e:
    r = 'СБОЙ выгрузки: %s %s' % (type(e).__name__, e)
print(json.dumps({'bajt': len(b), 'strok': {k: (len(v) if isinstance(v, list) else v) for k, v in out.items()},
                  'drop': r[:200]}, ensure_ascii=False))
'''
dest = r'C:\sender\pisma_dump_3s.py'
R.submit('enrich_contacts', {'op': 'panel_file_put',
         'files': [{'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'timeout': 600}, timeout=900)
d = r.get('data') or {}
print('rc', d.get('rc'))
print((d.get('stdout_tail') or d.get('stderr_tail') or '')[:2000])
