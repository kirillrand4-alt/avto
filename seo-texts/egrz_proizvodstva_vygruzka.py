# -*- coding: utf-8 -*-
"""Прямая выгрузка по СЛОВАМ ПРОИЗВОДСТВА из всего ЕГРЗ.

Портфельный заход показал главное: слова производства работают там, где слово
«компрессор» молчит. 372 такие карточки нашлись внутри одной выборки в 9 467 записей.
Здесь те же слова берутся по ВСЕМУ реестру — по замеру это около 13 тысяч записей.

Берутся ВСЕ 123 слова с ненулевой отдачей, включая заведомо шумные («молоч» 1 387,
«кирпичн» 673). Правило владельца: берём всё, сортируем потом; разделять, а не отсеивать.
Шум уйдёт в свой класс с причиной, а не в мусорное ведро.

Контроль: выдуманное слово «нипрятозаумень» обязано дать 0.
Полнота: каждый срез проверяется, и недобор печатается явно — неполная выгрузка
выглядит как вывод и тем опасна.
"""
import csv
import io
import json
import os
import re
import subprocess
import time

KAT = os.path.dirname(os.path.abspath(__file__))
BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'
ZAMER = os.path.join(KAT, 'ZAMER-KANDIDATOV.csv')
UZHE = [os.path.join(KAT, 'EGRZ-NASHA-TEMA-2.jsonl'),
        os.path.join(KAT, 'PORTFEL-RAZOBRANO.jsonl')]
VYHOD = os.path.join(KAT, 'PROIZVODSTVA-SYRYO.jsonl')
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
        time.sleep(3 + att * 5)
    return None


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


uzhe = set()
for p in UZHE:
    if os.path.exists(p):
        for s in io.open(p, encoding='utf-8'):
            if s.strip():
                uzhe.add(json.loads(s).get('ssylka', ''))
print('карточек уже есть (оба прошлых захода): %d' % len(uzhe))

SLOVA = [(x['slovo'], int(x['vsego'])) for x in
         csv.DictReader(io.open(ZAMER, encoding='utf-8-sig'), delimiter=';')
         if x['vsego'].isdigit() and int(x['vsego']) > 0]
SLOVA.sort(key=lambda z: z[1])
print('слов к выгрузке: %d, записей по замеру: %d (с пересечениями)'
      % (len(SLOVA), sum(n for _, n in SLOVA)))

d = zapros("contains(tolower(ExpertiseObjectName),'%s')" % KONTROL, top=1, schet=True)
print('КОНТРОЛЬ «%s»: %s записей' % (KONTROL, (d or {}).get('@odata.count')))

vse, nedobor = {}, []
for n, (slovo, zhdem) in enumerate(SLOVA, start=1):
    f = "contains(tolower(ExpertiseObjectName),'%s')" % slovo
    vzyato = 0
    for skip in range(0, zhdem, 100):
        d = zapros(f, 100, skip)
        if not d:
            nedobor.append((slovo, 'срез skip=%d не взят' % skip))
            continue
        for z in (d.get('value') or []):
            k = z.get('Key')
            if not k:
                continue
            if k not in vse:
                z['_po'] = slovo
                vse[k] = z
            elif slovo not in vse[k]['_po']:
                vse[k]['_po'] += ', ' + slovo
        vzyato += len(d.get('value') or [])
        time.sleep(0.2)
    if vzyato < zhdem:
        nedobor.append((slovo, 'взято %d из %d' % (vzyato, zhdem)))
    if n % 20 == 0 or n == len(SLOVA):
        print('  %3d/%d слов · карточек в наборе %d' % (n, len(SLOVA), len(vse)))

stroki = []
for z in vse.values():
    zastr = razobrat(z.get('DeveloperOrganizations'))
    proekt = razobrat(z.get('PlannerOrganizations'))
    tehz = razobrat(z.get('TechnicalCustomerOrganizations'))
    ssylka = 'https://egrz.ru/organisation/reestr/detail/' + str(z.get('Key') or '')
    stroki.append({
        'klass': '', 'pochemu': '', 'otrasl': '',
        'data': str(z.get('ExpertiseConclusionDate') or '')[:10],
        'region': z.get('SubjectRf') or '',
        'obekt': re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectName') or ''))[:700],
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
        'novaya_kartochka': 'нет' if ssylka in uzhe else 'да',
        'nomer_zaklyucheniya': z.get('ExpertiseNumber') or '',
        'ssylka': ssylka,
    })

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for s in stroki:
        f.write(json.dumps(s, ensure_ascii=False) + '\n')

print('\n########## СБОР')
print('  карточек собрано ............ %d' % len(stroki))
print('  из них НОВЫХ для нас ........ %d' % len([s for s in stroki if s['novaya_kartochka'] == 'да']))
print('  разных ИНН застройщика ...... %d' % len({s['zastroyshchik_inn'] for s in stroki if s['zastroyshchik_inn']}))
print('  НЕДОБОР (выгрузка неполная): %d случаев' % len(nedobor))
for x in nedobor[:15]:
    print('     %s' % (x,))
print('  файл: %s' % VYHOD)
