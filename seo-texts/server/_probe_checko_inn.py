# -*- coding: utf-8 -*-
import json, os, sys, re, urllib.request
sys.path.insert(0, r'C:\sender\server')
import cc_checko_proxy as CP
пп = [CP.Прокси(п) for п in json.load(open(r'C:\sender\server\checko-proxies.json'))]
o = []
for инн in ('5045016560', '7724766868'):
    for п in пп:
        try:
            r = п.op.open(urllib.request.Request('https://checko.ru/search?query=%s' % инн, headers=CP.H), timeout=40)
            html = r.read().decode('utf-8', 'replace')
            т = CP.текст(html)
            м = re.search(r'Основной вид деятельности.{0,200}', т)
            o.append({'inn': инн, 'код': r.status, 'url': r.geturl(), 'осн': м.group(0)[:200] if м else '', 'окв': CP.окведы(т)[:3]})
            break
        except Exception as e:
            o.append({'inn': инн, 'ошибка': repr(e)[:100]})
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
