# -*- coding: utf-8 -*-
r"""fixBX: какие воронки сделок видит пользователь вебхука Битрикс24 (только чтение; ссылка – из настроек сервера).

    python3 zapusk_na_servere.py fixBX_voronki.py
"""
import io
import json
import urllib.parse
import urllib.request

B = io.open(r'C:\centro2\data\bitrix-webhook.secret', encoding='utf-8').read().strip()


def vyzov(metod, **params):
    q = urllib.parse.urlencode(params, doseq=True)
    try:
        with urllib.request.urlopen(B + metod + '.json' + ('?' + q if q else ''), timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8') or '{}')


o = vyzov('crm.category.list', entityTypeId=2)
kat = (o.get('result') or {}).get('categories', [])
print('crm.category.list: всего %s, ошибка %s' % (o.get('total'), o.get('error')))
for c in kat:
    print('  %s = %s%s' % (c.get('id'), c.get('name'), ' (основная)' if c.get('isDefault') else ''))
o = vyzov('crm.dealcategory.list', **{'order[SORT]': 'ASC'})
print('\ncrm.dealcategory.list: всего %s, ошибка %s' % (o.get('total'), o.get('error')))
for c in o.get('result') or []:
    print('  %s = %s' % (c.get('ID'), c.get('NAME')))
o = vyzov('crm.dealcategory.default.get')
print('\nосновная воронка:', o.get('result') or o.get('error'))
for cid in (13, 0):
    o = vyzov('crm.dealcategory.stage.list', id=cid)
    print('стадии воронки %s: %s' % (cid, o.get('error') or ['%s=%s' % (x.get('STATUS_ID'), x.get('NAME')) for x in o.get('result') or []][:12]))
