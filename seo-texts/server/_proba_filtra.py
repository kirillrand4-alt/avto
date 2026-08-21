# -*- coding: utf-8 -*-
r"""Проба фильтра направления: и в бандле, и на живом API.

Проверяем не «собралось», а результат: письмо #3585 компрессорное, значит в
очереди Meyer его быть НЕ должно, а в очереди КЦ — должно.
"""
import json
import os
import re
import urllib.error
import urllib.request

d = {}
dist = r'C:\sender\web\dist\assets'
for ф in sorted(os.listdir(dist)):
    if not ф.endswith('.js'):
        continue
    with open(os.path.join(dist, ф), encoding='utf-8', errors='replace') as fh:
        т = fh.read()
    i = т.find('"confirm-queue"')
    if i < 0:
        i = т.find('confirm/queue')
    if i >= 0:
        d.setdefault('бандл', {})[ф] = {
            'кусок': т[max(0, i - 200):i + 320],
            'division_рядом': 'division' in т[max(0, i - 300):i + 400]}

# токен панели
токен = ''
try:
    with open(r'C:\sender\sender.yaml', encoding='utf-8') as f:
        for s in f:
            m = re.search(r'^\s*(api_token|token|panel_token)\s*:\s*(.+)$', s)
            if m:
                токен = m.group(2).strip().strip('"\'')
                break
except Exception as e:  # noqa: BLE001
    d['yaml'] = str(e)[:80]
d['токен_найден'] = bool(токен)


def взять(url):
    зпр = urllib.request.Request(url)
    if токен:
        зпр.add_header('X-Api-Token', токен)
        зпр.add_header('Authorization', 'Bearer ' + токен)
    try:
        o = urllib.request.urlopen(зпр, timeout=60)
        return o.status, json.loads(o.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:200]
    except Exception as e:  # noqa: BLE001
        return 'ошибка', str(e)[:160]


for напр in ('meyer', 'kc', ''):
    к, тело = взять('http://127.0.0.1:8091/api/confirm/queue?limit=50'
                    + ('&division=' + напр if напр else ''))
    если = {'код': к}
    if isinstance(тело, dict):
        писем = тело.get('pending') or []
        если['писем'] = len(писем)
        если['всего_в_очереди'] = тело.get('total')
        если['есть_3585'] = any(int(p.get('id') or 0) == 3585 for p in писем)
        если['первые_темы'] = [str(p.get('subject') or '')[:52] for p in писем[:3]]
    else:
        если['тело'] = тело
    d['очередь_%s' % (напр or 'все')] = если
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
