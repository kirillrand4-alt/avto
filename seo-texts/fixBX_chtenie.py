# -*- coding: utf-8 -*-
r"""fixBX: может ли вебхук ЧИТАТЬ лиды из Битрикса (только чтение; ссылка – из настроек сервера, не печатается).

    python3 zapusk_na_servere.py fixBX_chtenie.py [ID лида]
"""
import io
import json
import sys
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


lid = sys.argv[1] if len(sys.argv) > 1 else '379918'
o = vyzov('crm.lead.get', id=lid)
r = o.get('result') or {}
print('crm.lead.get %s:' % lid, ('ОШИБКА %r %r' % (o.get('error'), o.get('error_description'))) if not r else
      {k: r.get(k) for k in ('TITLE', 'STATUS_ID', 'SOURCE_ID', 'ASSIGNED_BY_ID', 'DATE_CREATE', 'DATE_MODIFY')})
o = vyzov('crm.lead.list', **{'select[]': ['ID', 'TITLE', 'STATUS_ID'], 'order[ID]': 'DESC', 'filter[SOURCE_ID]': '149'})
print('crm.lead.list (источник 149):', ('ОШИБКА %r %r' % (o.get('error'), o.get('error_description'))) if o.get('error') is not None and not o.get('result')
      else 'всего %s, первые: %s' % (o.get('total'), [(x.get('ID'), x.get('TITLE'), x.get('STATUS_ID')) for x in (o.get('result') or [])[:5]]))
