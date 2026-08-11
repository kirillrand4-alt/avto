# -*- coding: utf-8 -*-
"""ТУПИК: 2 040 карточек организации ЕИС, где мой разбор сказал «нет ни одной подписи о
контактах». Число крупное — значит повод проверить прибор, а не принять объяснение.

Правило владельца про тупик: идти к провайдеру ВЕЕРОМ ЛИНЗ, а не одним запросом. Здесь
первый шаг веера — добыть САМ ТЕКСТ этих карточек, чтобы было что показывать линзам.
Забираю 20 карточек: тяну их тем же способом, что сборщик, и сохраняю текст целиком.

Заслон на сам этот шаг: беру только те ИНН, по которым сборщик дошёл ДО карточки (то есть
ссылка в выдаче была) и уперся именно в подписи. Если бы я взяла ИНН без карточки, я бы
мерила другую беду.
"""
import csv, io, json, os, re, ssl, time, urllib.parse, urllib.request
OPS = r'C:\sender\_ops'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
KARTA = re.compile(r'href="(/epz/organization/view[^"]*?)"')
PODPISI = ('Контактное лицо', 'Ответственное должностное лицо', 'Телефон',
           'Контактная информация', 'Адрес электронной почты')
uzhe = set()
for f in ('PARK-EIS-ORG-OCHERED-3S.jsonl',):
    p = os.path.join(OPS, f)
    if os.path.exists(p):
        for s in io.open(p, encoding='utf-8', errors='replace'):
            try: uzhe.add(str(json.loads(s).get('inn') or ''))
            except Exception: pass
celi = []
with io.open(os.path.join(OPS, 'PARK-BEZ-KONTAKTA-3S.csv'), encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        i = (r.get('inn') or '').strip()
        if i.isdigit() and i not in uzhe:
            celi.append((i, (r.get('predpriyatie') or '')[:60]))
VYHOD = os.path.join(OPS, 'PARK-EIS-KARTOCHKI-TEKST-3S.jsonl')
vzyato = 0
sch = {}
with io.open(VYHOD, 'w', encoding='utf-8') as out:
    for inn, imya in celi:
        if vzyato >= 20:
            break
        u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
             '&morphology=on&sortBy=UPDATE_DATE' % inn)
        try:
            h = net.open(urllib.request.Request(u, headers={'User-Agent': UA}),
                         timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            sch['выдача не открылась'] = sch.get('выдача не открылась', 0) + 1
            continue
        m = KARTA.search(h)
        if not m:
            sch['в выдаче нет карточки'] = sch.get('в выдаче нет карточки', 0) + 1
            continue
        ku = 'https://zakupki.gov.ru' + m.group(1).replace('&amp;', '&')
        try:
            k = net.open(urllib.request.Request(ku, headers={'User-Agent': UA}),
                         timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            sch['карточка не открылась'] = sch.get('карточка не открылась', 0) + 1
            continue
        t = re.sub(r'\s+', ' ', TEG.sub(' ', k)).strip()
        if not re.search(r'ИНН[^0-9]{0,12}' + re.escape(inn), t):
            sch['ИНН после слова не стоит — чужая'] = sch.get('ИНН после слова не стоит — чужая', 0) + 1
            continue
        est = [p for p in PODPISI if p in t]
        out.write(json.dumps({'inn': inn, 'predpriyatie': imya, 'ssylka': ku,
                              'podpisi_moi': est, 'znakov': len(t), 'tekst': t[:9000]},
                             ensure_ascii=False) + '\n')
        vzyato += 1
        sch['ВЗЯТО, подписей у меня %d' % len(est)] = sch.get('ВЗЯТО, подписей у меня %d' % len(est), 0) + 1
print('########## ЧИСЛА')
print('  целей в очереди (не тронутых прошлым прогоном) %5d' % len(celi))
for k, v in sorted(sch.items(), key=lambda x: -x[1]):
    print('  %-52s %5d' % (k[:52], v))
print('  текстов сохранено %d -> %s' % (vzyato, VYHOD))
