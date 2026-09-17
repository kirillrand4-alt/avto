# -*- coding: utf-8 -*-
"""ЕГРЗ по нашей теме: шире словом и чище разбором.

Владелец: «там есть полезное, расширяй, только и почисть от мусора тоже» — и обвёл в
таблице строку «Реконструкция участков водопроводной сети … до ул. Компрессорная, 1».
То есть слово поймало УЛИЦУ, а не машину. Это главный класс мусора, и он не один.

ЧТО ИЗМЕНЕНО ПРОТИВ ПЕРВОГО ЗАХОДА
  1. Слов 15 вместо 5. Отдача каждого измерена ОТДЕЛЬНО, слово с нулём в список не идёт:
     компрессор 454 · агнкс 578 · газонаполнительн 235 · кислородн 157 · пневмо 78 ·
     нагнетател 67 · дожимн 64 · аммиачн 54 · азотн 46 · воздухораздел 16 ·
     воздуходувн 16 · сжатого воздуха 12 · холодильно-компрессорн 6 ·
     турбокомпрессор 2 · газоперекачива 2.
  2. Ловушка склейки слов: искать надо ПОДСТРОКУ, а не основу через пробел. «кислородн
     станц» даёт 0, потому что в тексте стоит «кислородная станция» — между ними «ая».
     Первый заход на этом потерял 157 записей по кислороду и 46 по азоту.
  3. Каждая запись получает КЛАСС, и мусор не выбрасывается, а уходит в свой лист со
     своей причиной — правило владельца «разделять, а не отсеивать».

КЛАССЫ МУСОРА, названные по образцам:
  адрес-улица       «ул. Компрессорная», «пер. Компрессорный» — слово только в адресе
  имя подстанции    «ПС 220 кВ Компрессорная» — так называется подстанция
  изготовитель      «Завод по производству центробежных компрессоров»,
                    «Испытательный комплекс Казанькомпрессормаш» — это КОНКУРЕНТ, не клиент
  соцобъект         парк, каток, депо, школа — компрессор там бытовой
Контроль: выдуманное слово обязано дать 0 записей.
"""
import io
import json
import os
import re
import subprocess
import time
import urllib.parse

BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'
VYHOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'EGRZ-NASHA-TEMA.jsonl')
SLOVA = ['компрессор', 'агнкс', 'газонаполнительн', 'кислородн', 'пневмо', 'нагнетател',
         'дожимн', 'аммиачн', 'азотн', 'воздухораздел', 'воздуходувн', 'сжатого воздуха',
         'холодильно-компрессорн', 'турбокомпрессор', 'газоперекачива']
KONTROL = 'нипрятозаумень'


def zapros(f, top=100, skip=0, schet=False):
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
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 + att * 4)
    print('   ОТКАЗ после 4 попыток')
    return None


# ------------------------------------------------------------------ разбор организаций
def razobrat(v):
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
        adr = re.search(r'МЕСТО НАХОЖДЕНИЯ и АДРЕС:\s*(.*?)\s*\)?$', s, re.S)
        out.append((re.split(r'\s*\(ОГРН', s)[0].strip(),
                    inn.group(1) if inn else '',
                    re.sub(r'\s+', ' ', adr.group(1)) if adr else ''))
    return out


# ------------------------------------------------------------------ классификатор
ADRES = re.compile(r'(?:ул\.?|улиц\w*|пер\.?|переул\w*|проезд|шоссе|пр-?кт|проспект|'
                   r'б-?р|бульвар|наб\.?|набережн\w*)\s*[«"]?компрессорн', re.I)
ADRES2 = re.compile(r'компрессорн\w*\s*,\s*(?:д\.?\s*)?\d', re.I)
PODSTANCIYA = re.compile(r'(?:пс|подстанц\w*)\s*[\d\s]*(?:кв)?\s*[«"]?компрессорн', re.I)
IZGOTOVITEL = re.compile(r'компрессормаш|завод\w*\s+по\s+производству[^.]{0,60}компрессор|'
                         r'производств\w+\s+компрессор|испытательн\w+\s+(?:комплекс|стенд)'
                         r'[^.]{0,40}компрессор', re.I)
SOC = re.compile(r'парк\s+культуры|пкио|каток|ледов\w+|депо|школ\w|детск\w+\s+сад|'
                 r'больниц|поликлиник|стадион|бассейн|жилой\s+дом|многоквартирн', re.I)
SET = re.compile(r'водопроводн\w+\s+сет|канализац|тепловая\s+сет|автомобильн\w+\s+дорог|'
                 r'линейн\w+\s+объект|газопровод\w*\s+низкого', re.I)
AGNKS = re.compile(r'агнкс|газонаполнительн|газозаправочн|криогенн\w+\s+азс|кпг', re.I)
NASHA = re.compile(r'компрессорн\w*\s+(?:станц|установк|цех|отделен|хозяйств)|'
                   r'станц\w*\s+компрессорн|компрессорная|компрессорной|компрессорную|'
                   r'воздухораздел|кислородн\w*\s+станц|азотн\w*\s+станц|'
                   r'станц\w*\s+сжатого\s+воздуха|дожимн\w*\s+компрессорн|нагнетател|'
                   r'газоперекачива|турбокомпрессор|воздуходувн|аммиачн\w*\s+холодильн|'
                   r'холодильно-компрессорн|компрессор', re.I)


def klass(obekt):
    t = re.sub(r'\s+', ' ', obekt or '')
    tl = t.lower()
    est_komp = 'компрессор' in tl or 'нагнетател' in tl or 'воздухораздел' in tl
    # 1. слово стоит только в адресе
    if est_komp and (ADRES.search(t) or ADRES2.search(t)):
        bez = ADRES.sub(' ', ADRES2.sub(' ', t))
        if 'компрессор' not in bez.lower():
            return 'мусор: адрес-улица', 'слово «компрессорная» стоит только в адресе объекта'
    if PODSTANCIYA.search(t):
        return 'мусор: имя подстанции', 'так называется подстанция, а не машина'
    if IZGOTOVITEL.search(t):
        return 'мусор: изготовитель компрессоров', 'это конкурент или его площадка, не клиент'
    if AGNKS.search(t):
        return 'АГНКС и газозаправка', 'газонаполнительная станция: компрессор есть, но это отдельный рынок'
    if SOC.search(t) and est_komp:
        return 'сомнительно: соцобъект', 'парк, депо, школа и подобное — машина скорее бытовая'
    if SET.search(t) and est_komp and not NASHA.search(t):
        return 'мусор: линейный объект', 'сети и дороги, компрессор упомянут мимоходом'
    if NASHA.search(t):
        return 'НАША ТЕМА', ''
    return 'сомнительно', 'ни один признак не сработал уверенно'


print('### Контроль')
d = zapros("contains(tolower(ExpertiseObjectName),'%s')" % KONTROL, top=1, schet=True)
print('  «%s» -> %s записей' % (KONTROL, (d or {}).get('@odata.count')))

vse = {}
for slovo in SLOVA:
    f = "contains(tolower(ExpertiseObjectName),'%s')" % slovo
    d = zapros(f, top=1, schet=True)
    n = (d or {}).get('@odata.count') or 0
    print('\n### «%s» — %s записей' % (slovo, n))
    for skip in range(0, int(n) + 1, 100):
        d = zapros(f, top=100, skip=skip)
        if not d:
            print('   срез skip=%d НЕ ВЗЯТ — выгрузка НЕПОЛНАЯ' % skip)
            continue
        for z in (d.get('value') or []):
            k = z.get('Key')
            if k not in vse:
                z['_po'] = slovo
                vse[k] = z
            elif slovo not in vse[k]['_po']:
                vse[k]['_po'] += ' | ' + slovo
        time.sleep(0.4)
    print('   в наборе после слова: %d' % len(vse))

stroki = []
for z in vse.values():
    ob = re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectName') or ''))
    kl, prich = klass(ob)
    zastr = razobrat(z.get('DeveloperOrganizations'))
    proekt = razobrat(z.get('PlannerOrganizations'))
    tehz = razobrat(z.get('TechnicalCustomerOrganizations'))
    stroki.append({
        'klass': kl, 'pochemu': prich,
        'data': str(z.get('ExpertiseConclusionDate') or '')[:10],
        'region': z.get('SubjectRf') or '',
        'obekt': ob[:700],
        'adres_obekta': re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectAddress') or ''))[:300],
        'vyvod': z.get('ExpertiseResultType') or '',
        'vid_dokumenta': z.get('ExpertiseDocumentType') or '',
        'zastroyshchik': zastr[0][0] if zastr else '',
        'zastroyshchik_inn': zastr[0][1] if zastr else '',
        'zastroyshchik_adres': zastr[0][2] if zastr else '',
        'proektirovshchik': proekt[0][0] if proekt else '',
        'proektirovshchik_inn': proekt[0][1] if proekt else '',
        'proektirovshchik_adres': proekt[0][2] if proekt else '',
        'tehzakazchik': tehz[0][0] if tehz else '',
        'tehzakazchik_inn': tehz[0][1] if tehz else '',
        'nayden_po': z.get('_po', ''),
        'nomer_zaklyucheniya': z.get('ExpertiseNumber') or '',
        'ssylka': 'https://egrz.ru/organisation/reestr/detail/' + str(z.get('Key') or ''),
    })

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for s in stroki:
        f.write(json.dumps(s, ensure_ascii=False) + '\n')

import collections
c = collections.Counter(s['klass'] for s in stroki)
print('\n########## ЧИСЛА')
print('  записей всего ............... %d' % len(stroki))
for k, n in c.most_common():
    print('    %-34s %5d' % (k, n))
nash = [s for s in stroki if s['klass'] == 'НАША ТЕМА']
print('  в «нашей теме»: ИНН застройщика %d, ИНН проектировщика %d, разных застройщиков %d'
      % (len([s for s in nash if s['zastroyshchik_inn']]),
         len([s for s in nash if s['proektirovshchik_inn']]),
         len({s['zastroyshchik_inn'] for s in nash if s['zastroyshchik_inn']})))
print('  файл: %s' % VYHOD)

print('\n########## ПО ПЯТЬ ОБРАЗЦОВ КАЖДОГО КЛАССА — СМОТРЮ ГЛАЗАМИ')
for k, _n in c.most_common():
    print('\n--- %s' % k)
    for s in [x for x in stroki if x['klass'] == k][:5]:
        print('   %s | %s' % (s['data'], s['obekt'][:120]))
