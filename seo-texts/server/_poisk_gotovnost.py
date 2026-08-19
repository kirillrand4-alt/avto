# -*- coding: utf-8 -*-
r"""Готовность к поиску сайтов: сколько целей, есть ли ключи, что с балансом.

Считаем ДО запуска, потому что каждый запрос платный: 25 рублей за тысячу.
"""
import json
import os
import sys
import urllib.request

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)

итог = {}
итог['ключи'] = {
    'XMLRIVER_USER': bool(os.environ.get('XMLRIVER_USER')),
    'XMLRIVER_KEY': bool(os.environ.get('XMLRIVER_KEY')),
    'PROVIDER_API_KEY': bool(os.environ.get('PROVIDER_API_KEY')),
}
итог['холды'] = {и: os.path.exists(os.path.join(DIR, и))
                 for и in ('HOLD-POISK.flag', 'HOLD-FAKTY.flag')}

лог = r'C:\sender\poisk_saytov.jsonl'
если_лог = {'строк': 0, 'нашли': 0, 'не_нашли': 0}
причины = {}
if os.path.exists(лог):
    with open(лог, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            если_лог['строк'] += 1
            if d.get('site'):
                если_лог['нашли'] += 1
            else:
                если_лог['не_нашли'] += 1
                п = str(d.get('src') or '')[:28]
                причины[п] = причины.get(п, 0) + 1
если_лог['почему_не_нашли_топ'] = dict(
    sorted(причины.items(), key=lambda x: -x[1])[:10])
итог['лог_прошлых_поисков'] = если_лог

try:
    import poisk_saytov as PS
    цели, порог, верх = PS.цели(10 ** 9)
    итог['целей_сейчас'] = len(цели)
    итог['рублей_примерно'] = round(len(цели) * 25 / 1000)
    итог['первые'] = [{'инн': c['inn'], 'имя': c['name'][:44],
                       'выручка_млн': round(c['revenue'] / 1e6, 1)} for c in цели[:5]]
except Exception as e:  # noqa: BLE001
    итог['цели_сбой'] = '%s: %s' % (type(e).__name__, e)

u, k = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
if u and k:
    try:
        r = urllib.request.urlopen(
            'http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (u, k),
            timeout=25).read().decode('utf-8', 'replace')
        итог['баланс_xmlriver'] = r.strip()[:200]
    except Exception as e:  # noqa: BLE001
        итог['баланс_сбой'] = str(e)[:120]

print(json.dumps(итог, ensure_ascii=False, indent=1))
