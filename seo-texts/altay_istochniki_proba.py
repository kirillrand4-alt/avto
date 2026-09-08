# -*- coding: utf-8 -*-
"""Проба источников под задачу «Алтайский край + компрессорное оборудование».

Список источников без проверки достижимости — это пожелание, а не план. Здесь каждый
кандидат получает один живой запрос С СЕРВЕРА и отвечает на два вопроса:
   1) отвечает ли хост вообще (код ответа; код ошибки — это ОТВЕТ, а не отсутствие связи);
   2) отдаёт ли он что-то осмысленное по слову «компрессор» с фильтром по региону 22.

У каждого запроса, где это возможно, идёт КОНТРОЛЬ выдуманным словом: если по «щварцкопфер»
находится столько же, сколько по «компрессору», значит фильтр не фильтрует и числу верить
нельзя. Эта проверка уже дважды спасала меня от выдуманных нулей и выдуманных находок.
"""
import json
import re
import ssl
import urllib.parse
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')


def dostat(u, telo=None, zagolovki=None):
    h = {'User-Agent': UA, 'Accept': 'application/json, text/html'}
    h.update(zagolovki or {})
    if telo is not None:
        h['Content-Type'] = 'application/json'
    try:
        r = net.open(urllib.request.Request(u, data=telo, headers=h), timeout=50)
        return r.getcode(), r.read(600000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:110]


print('### A. ЕИС: поиск по 44/223-ФЗ с фильтром по субъекту (Алтайский край, код 22)\n')
for slovo in ('компрессор', 'техническое обслуживание компрессор', 'щварцкопфер'):
    u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString='
         + urllib.parse.quote(slovo)
         + '&morphology=on&search-filter=%D0%94%D0%B0%D1%82%D0%B5+%D1%80%D0%B0%D0%B7%D0%BC'
           '%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D1%8F&pageNumber=1&sortDirection=false&recordsPerPage='
           '_50&showLotsInfoHidden=false&sortBy=UPDATE_DATE&fz44=on&fz223=on'
           '&customerPlace=5277&customerPlaceCodes=22')
    kod, t = dostat(u)
    m = re.search(r'Найдено\s*<span[^>]*>\s*([\d\s ]+)', t)
    if not m:
        m = re.search(r'search-results__total[^>]*>\s*([\d\s ]+)', t)
    naideno = re.sub(r'\D', '', m.group(1)) if m else '?'
    print('  «%-38s» код %-3s знаков %7d  найдено извещений: %s'
          % (slovo[:38], kod, len(t), naideno))

print('\n### B. torgi.gov.ru — распродажа имущества (компрессор в лоте = машина была)\n')
for slovo in ('компрессор', 'щварцкопфер'):
    u = ('https://torgi.gov.ru/new/api/public/lotcards/search?text=' + urllib.parse.quote(slovo)
         + '&dynSubjRF=22&byFirstVersion=true&withFacets=false&size=20&page=0')
    kod, t = dostat(u)
    vsego = '?'
    try:
        d = json.loads(t)
        vsego = d.get('total')
        primery = [(str((x.get('lotName') or ''))[:70],
                    str(((x.get('seller') or {}).get('name') or ''))[:44],
                    ((x.get('seller') or {}).get('inn') or ''))
                   for x in (d.get('content') or [])[:5]]
    except Exception:  # noqa: BLE001
        primery = []
    print('  «%-14s» код %-3s знаков %7d  лотов: %s' % (slovo, kod, len(t), vsego))
    for nm, sel, inn in primery:
        print('       %-70s | %s %s' % (nm, sel, inn))

print('\n### C. Прочие реестры: отвечает ли хост вообще\n')
KANDIDATY = [
    ('Ростехнадзор (реестры)', 'https://www.gosnadzor.ru/'),
    ('ЕРКНМ, единый реестр проверок', 'https://proverki.gov.ru/portal'),
    ('Реестр ЭПБ monitor-pb', 'https://monitor-pb.ru/'),
    ('ГИСП, промышленность', 'https://gisp.gov.ru/'),
    ('Федресурс (банкротства)', 'https://bankrot.fedresurs.ru/'),
    ('Росаккредитация, реестры', 'https://pub.fsa.gov.ru/'),
    ('Бухотчётность ФНС', 'https://bo.nalog.gov.ru/'),
    ('РТС-тендер', 'https://www.rts-tender.ru/'),
    ('Сбербанк-АСТ', 'https://www.sberbank-ast.ru/'),
    ('B2B-Center', 'https://www.b2b-center.ru/'),
    ('ЭТП ГПБ', 'https://etpgpb.ru/'),
    ('ТЭК-Торг', 'https://www.tektorg.ru/'),
    ('Росэлторг', 'https://www.roseltorg.ru/'),
    ('ОТС.ру', 'https://otc.ru/'),
    ('Фабрикант', 'https://www.fabrikant.ru/'),
    ('ЕАТ «Березка»', 'https://agregatoreat.ru/'),
    ('Работа России (API)',
     'http://opendata.trudvsem.ru/api/v1/vacancies/region/2200000000000?text='
     + urllib.parse.quote('компрессор') + '&limit=5'),
    ('Портал Алтайского края, закупки', 'https://gz.alregn.ru/'),
]
for imya, u in KANDIDATY:
    kod, t = dostat(u)
    if kod == 0:
        print('  %-32s СВЯЗИ НЕТ: %s' % (imya, t[:60]))
    else:
        print('  %-32s код %-3s знаков %7d' % (imya, kod, len(t)))
