# -*- coding: utf-8 -*-
"""Кто строит КОМПРЕССОРНУЮ: выгрузка из ЕГРЗ с застройщиком И проектировщиком.

Заказ владельца: отдельная таблица по тем, кто строит компрессорные станции — сами
предприятия, их проектировщики, новостные поводы и телефоны, если есть технические роли.

Почему именно ЕГРЗ: в записи заключения экспертизы лежат обе стороны с ИНН — застройщик
(эксплуатант) и проектировщик. На стадии проекта оборудование выбирает проектировщик, и до
сих пор он у нас был предположением, а не строкой с ИНН.

Ловушки, уже оплаченные прогонами:
  * contains() РЕГИСТРОЗАВИСИМ — «компрессорная» строчными 208, с заглавной 65,
    через tolower() 274. Ищем только через tolower.
  * основа против словарной формы: «цементный завод» 15 против «цементн» 181.
  * egrz.ru требует legacy TLS renegotiation: без конфига OpenSSL curl отдаёт код 000,
    и источник выглядит закрытым.
Контроль: выдуманное слово «щварцкопфер» обязано дать 0 записей.
"""
import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
import subprocess
import urllib.request

BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
SLOVA = ['компрессор', 'воздухораздел', 'азотная станц', 'кислородная станц',
         'станция сжатого воздуха']
KONTROL = 'щварцкопфер'
VYHOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'KOMPRESSORNYE-EGRZ.jsonl')


def zapros(f, top=100, skip=0, schet=False):
    """Через curl, а НЕ через urllib.

    Мой первый прогон получил HTTP 500 на КАЖДОМ запросе, хотя тот же фильтр через curl
    минутой раньше отвечал 200. Значит дело не в реестре, а в моём клиенте: urllib шлёт
    другой набор заголовков. Вместо того чтобы гадать какой именно, беру то, что уже
    доказано работающим. Это тот же класс, что «ноль надо доказывать»: ошибка выглядела
    как отказ источника, а была моей.
    """
    args = ['curl', '-sS', '-m', '90', '--get',
            '--data-urlencode', '$filter=' + f,
            '--data-urlencode', '$top=' + str(top),
            '--data-urlencode', '$skip=' + str(skip)]
    if schet:
        args += ['--data-urlencode', '$count=true']
    args.append(BAZA)
    for att in range(4):
        try:
            r = subprocess.run(args, capture_output=True, timeout=120)
            t = r.stdout.decode('utf-8', 'replace')
            if t.startswith('{'):
                return json.loads(t)
            if att == 3:
                print('   ОТКАЗ: %s' % (t[:100] or r.stderr.decode('utf-8', 'replace')[:100]))
                return None
        except Exception as e:  # noqa: BLE001
            if att == 3:
                print('   ОТКАЗ после 4 попыток: %s' % str(e)[:90])
                return None
        time.sleep(3 + att * 4)
    return None


ORG = re.compile(r'^(.*?)\s*\((?:ОГРН:\s*(\d{13,15}))?,?\s*(?:ИНН:\s*(\d{10,12}))?'
                 r'(?:,\s*КПП:\s*\d+)?(?:,\s*МЕСТО НАХОЖДЕНИЯ и АДРЕС:\s*(.*?))?\)?\s*$', re.S)


def razobrat(v):
    """Список организаций -> список (название, ИНН, адрес). Имена полей не угадываю:
    строка приходит одним куском, разбираю её регулярным выражением и печатаю, что вышло."""
    out = []
    if not v:
        return out
    if isinstance(v, str):
        v = [v]
    for s in v:
        s = str(s).strip()
        if not s:
            continue
        inn = re.search(r'ИНН:\s*(\d{10,12})', s)
        ogrn = re.search(r'ОГРН:\s*(\d{13,15})', s)
        adr = re.search(r'МЕСТО НАХОЖДЕНИЯ и АДРЕС:\s*(.*?)\s*\)?$', s, re.S)
        imya = re.split(r'\s*\(ОГРН', s)[0].strip()
        out.append((imya, inn.group(1) if inn else '', ogrn.group(1) if ogrn else '',
                    re.sub(r'\s+', ' ', adr.group(1)) if adr else ''))
    return out


print('### Контроль: выдуманное слово')
d = zapros("contains(tolower(ExpertiseObjectName),'%s')" % KONTROL, top=1, schet=True)
print('  «%s» -> %s записей%s' % (KONTROL, d.get('@odata.count') if d else '—',
                                  '   ПРИБОР РАЗЛИЧАЕТ' if d and d.get('@odata.count') == 0
                                  else '   ВНИМАНИЕ: контроль пробит'))

vse = {}
for slovo in SLOVA:
    f = "contains(tolower(ExpertiseObjectName),'%s')" % slovo
    d = zapros(f, top=1, schet=True)
    vsego = (d or {}).get('@odata.count')
    print('\n### «%s» — записей в реестре: %s' % (slovo, vsego))
    if not vsego:
        continue
    vzyato = 0
    for skip in range(0, int(vsego) + 1, 100):
        d = zapros(f, top=100, skip=skip)
        if not d:
            print('   срез skip=%d НЕ ВЗЯТ — выгрузка НЕПОЛНАЯ' % skip)
            continue
        kus = d.get('value') or []
        for z in kus:
            k = z.get('Key') or z.get('ExpertiseNumber')
            if k not in vse:
                z['_nayden_po'] = slovo
                vse[k] = z
            else:
                vse[k]['_nayden_po'] += ' | ' + slovo
        vzyato += len(kus)
        print('   skip=%-5d взято %3d, всего в наборе %d' % (skip, len(kus), len(vse)))
        time.sleep(0.5)
    print('   итого по слову: %d' % vzyato)

print('\n### Разбор организаций')
stroki = []
for k, z in vse.items():
    zastr = razobrat(z.get('DeveloperOrganizations') or z.get('DeveloperOrganizationInfo'))
    proekt = razobrat(z.get('PlannerOrganizations') or z.get('PlannerOrganizationInfo'))
    tehzak = razobrat(z.get('TechnicalCustomerOrganizations')
                      or z.get('TechnicalCustomerOrganizationInfo'))
    stroki.append({
        'nomer_zaklyucheniya': z.get('ExpertiseNumber') or '',
        'data': str(z.get('ExpertiseConclusionDate') or '')[:10],
        'vyvod': z.get('ExpertiseResultType') or '',
        'vid_ekspertizy': z.get('ExpertiseType') or '',
        'vid_dokumenta': z.get('ExpertiseDocumentType') or '',
        'region': z.get('SubjectRf') or '',
        'obekt': re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectName') or ''))[:600],
        'adres_obekta': re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectAddress') or ''))[:300],
        'zastroyshchik': zastr[0][0] if zastr else '',
        'zastroyshchik_inn': zastr[0][1] if zastr else '',
        'zastroyshchik_adres': zastr[0][3] if zastr else '',
        'proektirovshchik': proekt[0][0] if proekt else '',
        'proektirovshchik_inn': proekt[0][1] if proekt else '',
        'proektirovshchik_adres': proekt[0][3] if proekt else '',
        'tehzakazchik': tehzak[0][0] if tehzak else '',
        'tehzakazchik_inn': tehzak[0][1] if tehzak else '',
        'ekspertnaya_org': re.sub(r'\s+', ' ', str(z.get('ExpertiseOrganizatioInfo') or ''))[:200],
        'nayden_po': z.get('_nayden_po', ''),
        'ssylka': 'https://egrz.ru/organisation/reestr/detail/' + str(z.get('Key') or ''),
    })

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for s in stroki:
        f.write(json.dumps(s, ensure_ascii=False) + '\n')

print('\n########## ЧИСЛА')
print('  записей всего .................... %d' % len(stroki))
print('  с ИНН застройщика ................ %d' % len([s for s in stroki if s['zastroyshchik_inn']]))
print('  с ИНН проектировщика ............. %d' % len([s for s in stroki if s['proektirovshchik_inn']]))
print('  с ИНН технического заказчика ..... %d' % len([s for s in stroki if s['tehzakazchik_inn']]))
print('  положительных заключений ......... %d' % len([s for s in stroki if 'оложительн' in s['vyvod']]))
print('  разных застройщиков (ИНН) ........ %d' % len({s['zastroyshchik_inn'] for s in stroki if s['zastroyshchik_inn']}))
print('  разных проектировщиков (ИНН) ..... %d' % len({s['proektirovshchik_inn'] for s in stroki if s['proektirovshchik_inn']}))
gody = {}
for s in stroki:
    gody[s['data'][:4]] = gody.get(s['data'][:4], 0) + 1
print('  по годам: %s' % ', '.join('%s:%d' % (g, n) for g, n in sorted(gody.items(), reverse=True)[:8]))
print('  файл: %s' % VYHOD)
print('\n  ДЕСЯТЬ СТРОК ГЛАЗАМИ:')
for s in stroki[:10]:
    print('   %s | %s | %s' % (s['data'], s['region'][:22], s['obekt'][:70]))
    print('      застройщик:     %-46s ИНН %s' % (s['zastroyshchik'][:46], s['zastroyshchik_inn']))
    print('      проектировщик:  %-46s ИНН %s' % (s['proektirovshchik'][:46], s['proektirovshchik_inn']))
