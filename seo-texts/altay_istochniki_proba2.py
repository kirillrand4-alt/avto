# -*- coding: utf-8 -*-
"""Добивка пробы: региональный портал Алтая и ПРАВИЛЬНЫЙ фильтр региона у torgi.gov.ru.

В первой пробе torgi ответил лотами «винтовой компрессор Remeza ВК15Е», но среди них лежали
участки в Чувашии — значит параметр `dynSubjRF=22` НЕ фильтровал, а я чуть не записала эти
лоты в алтайские. Проверяю варианты записи кода региона и смотрю, меняется ли выдача.
"""
import json, re, ssl, urllib.parse, urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
def dostat(u):
    try:
        r = net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                        'Accept': 'application/json'}), timeout=50)
        return r.getcode(), r.read(400000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:
        return 0, str(e)[:100]

print('### torgi.gov.ru: варианты фильтра региона, слово «компрессор»\n')
VARIANTY = [('без фильтра', ''), ('dynSubjRF=22', '&dynSubjRF=22'),
            ('dynSubjRF=2200000000000', '&dynSubjRF=2200000000000'),
            ('subjectRFCode=22', '&subjectRFCode=22'),
            ('dynSubjRF=01000000000', '&dynSubjRF=01000000000')]
for imya, hvost in VARIANTY:
    u = ('https://torgi.gov.ru/new/api/public/lotcards/search?text='
         + urllib.parse.quote('компрессор') + hvost + '&byFirstVersion=true&size=30&page=0')
    kod, t = dostat(u)
    vsego = regiony = '—'
    try:
        d = json.loads(t)
        vsego = d.get('total') if d.get('total') is not None else len(d.get('content') or [])
        reg = set()
        for x in (d.get('content') or []):
            r = x.get('subjectRFCode') or x.get('subjectRF') or ''
            if isinstance(r, dict):
                r = r.get('name') or r.get('code') or ''
            reg.add(str(r)[:26])
        regiony = ', '.join(sorted(reg)[:6])
    except Exception as e:
        pass
    print('  %-26s код %-3s знаков %6d  лотов %-5s  регионы в выдаче: %s'
          % (imya, kod, len(t), vsego, regiony))

print('\n### Региональный портал Алтайского края и соседние адреса\n')
for imya, u in (('Госзакупки Алтайского края', 'https://www.gzalt.ru/'),
                ('Портал поставщиков края', 'https://www.gzalt.ru/Folder/Folder.aspx?FP=187'),
                ('Минэкономразвития края (контрактная система)', 'https://econom22.ru/about/GosZakaz/index.php'),
                ('Сибирское управление Ростехнадзора', 'https://sib.gosnadzor.ru/'),
                ('Реестр ОПО (поиск)', 'https://www.gosnadzor.ru/industrial/objects/'),
                ('ФГИС Росаккредитации, декларации', 'https://pub.fsa.gov.ru/rds/declaration'),
                ('Проверки: ЕРКНМ поиск', 'https://proverki.gov.ru/portal/public-knm')):
    kod, t = dostat(u)
    print('  %-46s %s' % (imya, ('код %s, знаков %d' % (kod, len(t))) if kod else ('СВЯЗИ НЕТ: ' + t[:50])))
