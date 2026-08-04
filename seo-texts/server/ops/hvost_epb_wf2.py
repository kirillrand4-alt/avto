# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ. Проверка выводов по хвосту 23 строк EPB-pereprosheno.

Что доказываем:
  1) 27 дублей ключа в CSV лежат ЦЕЛИКОМ в видимой части (гипотеза «дубль
     схлопнут» не объясняет хвост);
  2) ведущий ноль ИНН не теряется (0268008010 и т.п. есть в company);
  3) для каждой из 27 недоехавших строк — причина ИЗ ОТСЕВА реального прогона
     доливки (ground truth конвейера), а не из моей симуляции;
  4) n=206 (компрессор синтез-газа поз.103-J) — есть ли на самом деле факт;
  5) что потеряется: сколько у этих ИНН уже воздушных центробежных фактов,
     не скрыты ли они, каков приговор суда.
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

БАЗА = r'C:\seostat\data\centrifugal.db'
ПРОДАЖИ = r'C:\seostat\data\centro_sales.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ПЕРЕПРОС = r'C:\sender\server\EPB-pereprosheno-centrobezhnye.csv'
ОТСЕВ = 'OTSEV-EPB-1-sessiya.csv'


def цифры(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def норм(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower())


def читать(путь):
    if not os.path.exists(путь):
        return []
    csv.field_size_limit(10 ** 7)
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        return list(csv.DictReader(ф, delimiter=';'))


def main():
    из = {}
    сыр = читать(ПЕРЕПРОС)
    строки = []
    for i, r in enumerate(сыр):
        и = цифры(r.get('inn'))
        об = (r.get('obekt') or '').strip()
        строки.append({'n': i + 1, 'inn_raw': (r.get('inn') or '').strip(),
                       'inn': и, 'predpr': (r.get('predpriyatie') or '').strip(),
                       'obekt': об, 'key': f'{и}|{об[:80]}'})
    по_ключу = defaultdict(list)
    for с in строки:
        по_ключу[с['key']].append(с)

    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=30)
    сырые_инн = {str(r[0]).strip() for r in cx.execute('SELECT inn FROM company')}
    компании = {цифры(и): n for и, n in cx.execute(
        'SELECT inn, predpriyatie FROM company')}
    факты = []
    for и, ц, ет, ев, ст, ср, ии in cx.execute(
            "SELECT inn, COALESCE(quote,''), COALESCE(equipment_type,''), "
            "COALESCE(evidence,''), COALESCE(status,''), COALESCE(medium,''), "
            "COALESCE(source,'') FROM fact"):
        факты.append({'inn': цифры(и), 'q': ц, 'et': ет, 'ev': ев,
                      'st': ст, 'md': ср, 'src': ии})
    cx.close()
    ключи_пер = {f"{ф['inn']}|{ф['q'][:80]}" for ф in факты
                 if 'перепрос провайдера' in ф['ev'] or 'перепрос' in ф['et']}
    факты_по_инн = defaultdict(list)
    for ф in факты:
        факты_по_инн[ф['inn']].append(ф)

    видно = [с for с in строки if с['key'] in ключи_пер]
    нет = [с for с in строки if с['key'] not in ключи_пер]
    дубли = {k: v for k, v in по_ключу.items() if len(v) > 1}
    дубль_строк = sum(len(v) - 1 for v in дубли.values())
    дубль_в_невидимых = sum(1 for с in нет if len(по_ключу[с['key']]) > 1)
    из['1_дубли'] = {
        'строк_csv': len(строки), 'уникальных_ключей': len(по_ключу),
        'лишних_строк_из_за_дублей': дубль_строк,
        'групп_дублей': len(дубли),
        'видно': len(видно), 'не_видно': len(нет),
        'из_НЕвидимых_имеют_близнеца': дубль_в_невидимых,
        'уникальных_ключей_среди_видимых': len({с['key'] for с in видно}),
    }

    # 2. ведущий ноль
    нули = [с for с in строки if с['inn_raw'].startswith('0')]
    из['2_vedushchiy_nol'] = {
        'строк_с_нулём': len(нули),
        'их_ИНН': sorted({с['inn_raw'] for с in нули}),
        'все_ли_в_company': all(с['inn'] in компании for с in нули),
        'сырые_ИНН_company_с_нулём': sorted(
            x for x in сырые_инн if x.startswith('0'))[:6],
        'фактов_у_них': {с: len(факты_по_инн[с])
                         for с in sorted({с['inn'] for с in нули})},
    }

    # 3. причина из отсева реального прогона
    отсев = {}
    for r in читать(os.path.join(ДРОП, ОТСЕВ)):
        и = цифры(r.get('inn'))
        об = (r.get('obekt') or '').strip()
        отсев[f'{и}|{об[:80]}'] = (r.get('prichina_otseva') or '').strip()
    строки_хвоста = []
    for с in нет:
        строки_хвоста.append({
            'n': с['n'], 'inn': с['inn_raw'], 'predpr': с['predpr'][:34],
            'prichina_otseva': отсев.get(с['key'], 'НЕТ В ОТСЕВЕ'),
            'obekt': с['obekt'][:96]})
    из['3_svod_prichin_iz_otseva'] = Counter(
        д['prichina_otseva'] for д in строки_хвоста).most_common()

    # 4. точечно: есть ли факты по спорным цитатам
    точечно = {}
    for метка, кусок, инн in (
            ('синтез-газ 103-J', 'синтез-газа', '2631015563'),
            ('ГТТ-3М', 'гтт-3м', '2631015563'),
            ('3VRZ кислород', '3vrz', '2631015563'),
            ('КТК-7/14', 'ктк-7/14', '0268008010'),
            ('КТК-12,5/35', 'ктк-12,5/35', '2124009521'),
            ('Н-540-41-1', 'н-540-41-1', '2631015563')):
        совп = [ф for ф in факты_по_инн[инн] if кусок in норм(ф['q'])
                or кусок in норм(ф['ev'])]
        точечно[метка] = {'фактов': len(совп),
                          'примеры': [{'et': ф['et'][:50], 'md': ф['md'],
                                       'q': ф['q'][:70]} for ф in совп[:3]]}
    из['4_est_li_fakt_po_spornym'] = точечно

    # 5. что потеряется
    потери = {}
    for инн in sorted({с['inn'] for с in нет}):
        сп = факты_по_инн[инн]
        воздух = [ф for ф in сп if ф['md'] == 'воздух']
        центро = [ф for ф in сп if 'центробеж' in норм(ф['et'])]
        потери[инн] = {
            'предприятие': компании.get(инн, 'НЕТ В COMPANY')[:44],
            'фактов_всего': len(сп),
            'из_них_центробежных': len(центро),
            'из_них_среда_воздух': len(воздух),
            'строк_хвоста': sum(1 for с in нет if с['inn'] == инн),
            'сред_в_фактах': Counter(ф['md'] or '(пусто)'
                                     for ф in сп).most_common(4),
        }
    из['5_chto_teryaem'] = потери

    # приговор суда и скрытия
    try:
        px = sqlite3.connect(f'file:{ПРОДАЖИ}?mode=ro', uri=True, timeout=30)
        инны = sorted({с['inn'] for с in нет})
        зн = ','.join('?' * len(инны))
        суд = {}
        try:
            for r in px.execute(
                    f'SELECT inn, verdikt, uverennost, pochemu FROM sud_verdikt '
                    f'WHERE inn IN ({зн})', инны):
                суд[str(r[0])] = {'verdikt': r[1], 'uv': r[2],
                                  'pochemu': (r[3] or '')[:90]}
        except Exception as e:  # noqa: BLE001
            суд = {'ошибка': str(e)[:80]}
        скрыт = {}
        try:
            for r in px.execute(
                    f'SELECT inn, COUNT(*) FROM hidden_item WHERE inn IN ({зн}) '
                    f'GROUP BY inn', инны):
                скрыт[str(r[0])] = r[1]
        except Exception as e:  # noqa: BLE001
            скрыт = {'ошибка': str(e)[:80]}
        px.close()
        из['6_sud_i_skrytiya'] = {'sud': суд, 'skryto_elementov': скрыт}
    except Exception as e:  # noqa: BLE001
        из['6_sud_i_skrytiya'] = f'нет доступа: {e}'

    полный = {'svodka': из, 'hvost_23_27': строки_хвоста}
    п = r'C:\sender\server\HVOST-EPB-wf2.json'
    with open(п, 'w', encoding='utf-8') as ф:
        json.dump(полный, ф, ensure_ascii=False, indent=1, default=str)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        import urllib.request
        урл = os.environ.get('DROP_URL',
                             'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/HVOST-EPB-wf2.json',
            data=open(п, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        хвост_печ = 'HVOST-EPB-wf2.json на дропе'
    except Exception as e:  # noqa: BLE001
        хвост_печ = f'на дроп не ушёл: {e}'
    print(json.dumps(из, ensure_ascii=False, indent=1, default=str)[:5200])
    print('\n' + хвост_печ)


if __name__ == '__main__':
    main()
