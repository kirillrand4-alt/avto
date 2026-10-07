# -*- coding: utf-8 -*-
import collections, json, sys, time
sys.path.insert(0, r'C:\sender\server')
import poisk_otbor as PO
t = time.time()
к, огрн, без = PO.кандидаты()
o = {'кандидатов': len(к), 'огрн_без_инн': len(огрн), 'сайтов_без_инн_с_юрименем': len(без), 'пример_без': без[:3]}
д = PO.доходы(set(к))
o['с_доходом'] = len(д); o['>=1.5'] = sum(1 for v in д.values() if v >= PO.ПОРОГ)
н = PO.наши_данные(set(к))
o['оквэд_известен'] = sum(1 for v in н.values() if v.get('осн'))
сег = collections.Counter()
нужно = 0
for i in к:
    v = н.get(i) or {}
    if д.get(i, 0) >= PO.ПОРОГ:
        if v.get('осн'):
            сег[PO.сегмент(v['осн'], v.get('все') or [v['осн']]) or '-'] += 1
        else:
            нужно += 1
o['>=1.5 по сегментам (оквэд известен)'] = dict(сег); o['>=1.5 нужно оквэд'] = нужно
o['сек'] = round(time.time() - t)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:4000])
