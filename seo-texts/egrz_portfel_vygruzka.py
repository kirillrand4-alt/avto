# -*- coding: utf-8 -*-
"""Выгрузка портфелей: все заключения 299 лиц «нашей темы», кроме гигантов.

Замер показал: через 329 лиц достижимо 26 513 заключений. Гиганты сюда не берутся —
30 лиц с портфелем больше 200 дают 15 733 записи, и это нефтегаз плюс ГКУ дорожного
строительства, попавшее в список из-за одной компрессорной. Берём 299 лиц с портфелем
до 200: 10 780 записей, около 406 запросов.

Синтаксис, без которого идея не работает (поля организаций — коллекции):
    PlannerOrganizations/any(o: contains(o,'ИНН'))
Обычный contains по такому полю отдаёт отказ, который выглядит как «ничего нет».

Здесь только сбор. Классы ставит тот же разбор, что дал 294 объекта:
    python3 pereklass.py PORTFEL-SYRYO.jsonl PORTFEL-RAZOBRANO.jsonl
Один классификатор на оба файла — иначе числа несравнимы.
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
LICA = os.path.join(KAT, 'PORTFEL-LIC.csv')
UZHE = os.path.join(KAT, 'EGRZ-NASHA-TEMA-2.jsonl')
VYHOD = os.path.join(KAT, 'PORTFEL-SYRYO.jsonl')
PREDEL = 200


def zapros(f, top=100, skip=0):
    args = ['curl', '-sS', '-m', '90', '--get',
            '--data-urlencode', '$filter=' + f,
            '--data-urlencode', '$top=' + str(top),
            '--data-urlencode', '$skip=' + str(skip), BAZA]
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
for s in io.open(UZHE, encoding='utf-8'):
    if s.strip():
        uzhe.add(json.loads(s).get('ssylka', ''))
print('уже есть карточек: %d' % len(uzhe))

lica = [x for x in csv.DictReader(io.open(LICA, encoding='utf-8-sig'), delimiter=';')
        if x['vsego_v_reestre'].isdigit() and 0 < int(x['vsego_v_reestre']) <= PREDEL]
print('лиц к выгрузке: %d, заключений по замеру: %d'
      % (len(lica), sum(int(x['vsego_v_reestre']) for x in lica)))

POLE = {'проектировщик': 'PlannerOrganizations', 'застройщик': 'DeveloperOrganizations'}
vse, nepolno = {}, []
for n, x in enumerate(lica, start=1):
    pole = POLE[x['rol']]
    f = "%s/any(o: contains(o,'%s'))" % (pole, x['inn'])
    zhdem = int(x['vsego_v_reestre'])
    vzyato = 0
    for skip in range(0, zhdem, 100):
        d = zapros(f, 100, skip)
        if not d:
            nepolno.append((x['inn'], x['rol'], skip))
            continue
        for z in (d.get('value') or []):
            k = z.get('Key')
            if k and k not in vse:
                z['_ot_kogo'] = '%s %s' % (x['rol'], x['inn'])
                vse[k] = z
            elif k:
                # лицо может встретиться и как проектировщик, и как застройщик — источники
                # НАКАПЛИВАЮТСЯ, а не заменяются
                t = '%s %s' % (x['rol'], x['inn'])
                if t not in vse[k]['_ot_kogo']:
                    vse[k]['_ot_kogo'] += ' | ' + t
        vzyato += len(d.get('value') or [])
        time.sleep(0.2)
    if vzyato < zhdem:
        nepolno.append((x['inn'], x['rol'], 'взято %d из %d' % (vzyato, zhdem)))
    if n % 25 == 0 or n == len(lica):
        print('  %3d/%d лиц · карточек в наборе %d' % (n, len(lica), len(vse)))

stroki = []
for z in vse.values():
    ob = re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectName') or ''))
    zastr = razobrat(z.get('DeveloperOrganizations'))
    proekt = razobrat(z.get('PlannerOrganizations'))
    tehz = razobrat(z.get('TechnicalCustomerOrganizations'))
    ssylka = 'https://egrz.ru/organisation/reestr/detail/' + str(z.get('Key') or '')
    stroki.append({
        'klass': '', 'pochemu': '',
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
        'nayden_po': z.get('_ot_kogo', ''),
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
print('  срезов не взято (выгрузка неполная): %d' % len(nepolno))
for x in nepolno[:10]:
    print('     %s' % (x,))
print('  файл: %s' % VYHOD)
