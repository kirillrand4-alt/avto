# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ. Почему из 228 строк EPB-pereprosheno-centrobezhnye.csv
в таблице fact видно 205: разобрать каждую недостающую строку по причине.

Проверяемые гипотезы (в порядке разбора):
  1) ключ строки схлопнут — в самом CSV две строки с одинаковым inn|obekt80;
  2) предприятия нет в company (панель его не знает / он выпал при пересборке);
  3) цитата в факте обрезана иначе (факт есть, ключ не сходится);
  4) ИНН с ведущим нулём потерян при чтении;
  5) строку срезал гейт доливки (среда газ / rejection_reason / нет в исходнике).

Ничего не пишет в базы. Запуск: python hvost_epb_wf.py
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\seostat')
try:
    from app.services import centro_medium as CM
except Exception:  # noqa: BLE001
    CM = None
try:
    from app.services import centro_marki as CMK
except Exception:  # noqa: BLE001
    CMK = None

БАЗА = r'C:\seostat\data\centrifugal.db'
ПРОДАЖИ = r'C:\seostat\data\centro_sales.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ПЕРЕПРОС = r'C:\sender\server\EPB-pereprosheno-centrobezhnye.csv'
ЖУРНАЛ = r'C:\sender\server\epb_perepros.jsonl'
ИСХОДНИК = 'VAZHNOE-3s-EPB-NASHI-MASHINY.csv'
ОТСЕВ = 'OTSEV-EPB-1-sessiya.csv'

_ГАЗ_ПРЕДПРИЯТИЕ = re.compile(
    r'трансгаз|газпром\s+добыч|подземн\w*\s+хранилищ\w*\s+газ|\bпхг\b|'
    r'газпром\s+переработк|газоперекачивающ', re.I)
_ГАЗ_МАШИНА = re.compile(
    r'\bцбн\b|\bгпа\b|газоперекачивающ|нагнетател\w*\s+(?:природн\w*\s+)?газ|'
    r'перекачк\w*\s+газ|магистральн\w*\s+газопровод|дожимн\w*\s+компрессорн|'
    r'компримировани\w*\s+газ|газов\w*\s+компрессор', re.I)
_ВОЗДУХ = re.compile(r'воздух\w*|воздушн\w*|\bair\b', re.I)
_ЦБ_В_ТЕКСТЕ = re.compile(
    r'центробежн|турбовоздуходувк|турбокомпрессор|турбоагрегат\w*\s+возду|'
    r'\bцк[\s-]?\d|\bк-?\d{3}-\d{2}|\b\d{2}вц[\s-]?\d|\bтв-?\d', re.I)


def цифры(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def норм(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower())


def среда(предприятие, текст):
    т = f'{предприятие} {текст}'
    if _ВОЗДУХ.search(текст or ''):
        return 'воздух'
    газ_п = bool(_ГАЗ_ПРЕДПРИЯТИЕ.search(предприятие or ''))
    газ_м = bool(_ГАЗ_МАШИНА.search(текст or ''))
    if газ_п and газ_м:
        return 'газ'
    if газ_м and re.search(r'\bгпа\b|газоперекачивающ|магистральн\w*\s+газопр'
                           r'|перекачк\w*\s+газ|газов\w*\s+компрессор', т, re.I):
        return 'газ'
    if газ_п and re.search(r'нагнетател|компрессор', текст or '', re.I):
        return 'газ'
    return ''


def читать_csv(путь):
    if not os.path.exists(путь):
        return []
    csv.field_size_limit(10 ** 7)
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        return list(csv.DictReader(ф, delimiter=';'))


def main():
    отчёт = {}
    # --- 1. сам CSV ---
    сыр = читать_csv(ПЕРЕПРОС)
    строки = []
    for i, r in enumerate(сыр):
        инн_сырой = (r.get('inn') or '').strip()
        и = цифры(инн_сырой)
        об = (r.get('obekt') or '').strip()
        строки.append({'n': i + 1, 'inn_raw': инн_сырой, 'inn': и,
                       'predpr': (r.get('predpriyatie') or '').strip(),
                       'obekt': об, 'pochemu': (r.get('pochemu') or '').strip(),
                       'key': f'{и}|{об[:80]}', 'nkey': f'{и}|{норм(об)[:80]}'})
    по_ключу = defaultdict(list)
    for с in строки:
        по_ключу[с['key']].append(с)
    отчёт['csv_строк'] = len(строки)
    отчёт['csv_уникальных_ключей'] = len(по_ключу)
    отчёт['csv_уникальных_инн'] = len({с['inn'] for с in строки})
    отчёт['csv_инн_с_ведущим_нулём'] = sum(
        1 for с in строки if с['inn_raw'].startswith('0'))
    отчёт['csv_инн_длина'] = Counter(len(с['inn']) for с in строки)

    # --- 2. панель ---
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=30)
    кол_ко = [c[1] for c in cx.execute('PRAGMA table_info("company")')]
    отчёт['колонки_company'] = кол_ко
    отчёт['колонки_fact'] = [c[1] for c in cx.execute('PRAGMA table_info("fact")')]
    имя_кол = next((k for k in ('name', 'short_name', 'title', 'company',
                                'naimenovanie', 'full_name')
                    if k in кол_ко), None)
    компании = {}
    выб = f"SELECT inn, COALESCE({имя_кол},'') FROM company" if имя_кол \
        else "SELECT inn, '' FROM company"
    for инн, назв in cx.execute(выб):
        компании[цифры(инн)] = назв
    сырые_инн_компаний = {str(r[0]).strip() for r in
                          cx.execute('SELECT inn FROM company')}
    факты = []
    for и, ц, ет, ев, ст, ии in cx.execute(
            "SELECT inn, COALESCE(quote,''), COALESCE(equipment_type,''), "
            "COALESCE(evidence,''), COALESCE(status,''), COALESCE(source,'') "
            "FROM fact"):
        факты.append({'inn': цифры(и), 'quote': ц, 'etype': ет,
                      'evid': ев, 'status': ст, 'src': ии})
    cx.close()
    отчёт['компаний_в_панели'] = len(компании)
    отчёт['фактов_всего'] = len(факты)

    перепрос_факты = [ф for ф in факты if 'перепрос провайдера' in ф['evid']
                      or 'перепрос' in ф['etype']]
    отчёт['фактов_с_меткой_перепроса'] = len(перепрос_факты)
    ключи_перепрос = {f"{ф['inn']}|{ф['quote'][:80]}" for ф in перепрос_факты}
    нключи_перепрос = {f"{ф['inn']}|{норм(ф['quote'])[:80]}"
                       for ф in перепрос_факты}
    ключи_все = {f"{ф['inn']}|{ф['quote'][:80]}" for ф in факты}
    нключи_все = {f"{ф['inn']}|{норм(ф['quote'])[:80]}" for ф in факты}
    факты_по_инн = defaultdict(list)
    for ф in факты:
        факты_по_инн[ф['inn']].append(ф)

    # --- 3. исходник и отсев ---
    исход = читать_csv(os.path.join(ДРОП, ИСХОДНИК))
    исход_по_ключу = defaultdict(list)
    for r in исход:
        и = цифры(r.get('inn'))
        об = (r.get('obekt') or '').strip()
        исход_по_ключу[f'{и}|{об[:80]}'].append(r)
    отсев_строк = читать_csv(os.path.join(ДРОП, ОТСЕВ))
    отсев_по_ключу = {}
    for r in отсев_строк:
        и = цифры(r.get('inn'))
        об = (r.get('obekt') or '').strip()
        отсев_по_ключу[f'{и}|{об[:80]}'] = (r.get('prichina_otseva') or '')
    отчёт['исходник_строк'] = len(исход)
    отчёт['отсев_строк'] = len(отсев_строк)

    # --- 4. журнал перепроса ---
    жур = Counter()
    жур_центро = set()
    if os.path.exists(ЖУРНАЛ):
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            жур[з.get('tip') or '?'] += 1
            if (з.get('tip') or '') == 'центробежный':
                жур_центро.add(з.get('kluch') or '')
    отчёт['журнал_итог'] = dict(жур)
    отчёт['журнал_центробежных_ключей'] = len(жур_центро)

    # --- 5. разбор каждой строки ---
    видно, нет = [], []
    покрытые_ключи = set()
    for с in строки:
        есть = (с['key'] in ключи_перепрос or с['nkey'] in нключи_перепрос)
        if есть:
            видно.append(с)
            покрытые_ключи.add(с['key'])
        else:
            нет.append(с)

    отчёт['видно_в_fact_с_меткой_перепроса'] = len(видно)
    отчёт['НЕ_видно'] = len(нет)

    разбор = []
    for с in нет:
        д = {'n': с['n'], 'inn': с['inn_raw'], 'predpr': с['predpr'][:60],
             'obekt': с['obekt'][:110]}
        причины = []
        # ведущий ноль
        if с['inn_raw'].startswith('0'):
            д['vedushchiy_nol'] = True
        if len(с['inn']) not in (10, 12):
            причины.append(f"битый ИНН (длина {len(с['inn'])})")
        # дубль ключа внутри CSV
        близнецы = [t for t in по_ключу[с['key']] if t['n'] != с['n']]
        if близнецы:
            д['bliznecov_v_csv'] = len(близнецы)
            if с['key'] in покрытые_ключи or any(
                    t['key'] in ключи_перепрос for t in близнецы):
                причины.append('дубль ключа в CSV: строку покрыл близнец')
            else:
                причины.append('дубль ключа в CSV (обе строки не доехали)')
        # компания
        if с['inn'] not in компании:
            вар = [x for x in компании
                   if x.lstrip('0') == с['inn'].lstrip('0') and x != с['inn']]
            причины.append('предприятия НЕТ в company'
                           + (f' (есть вариант {вар[0]})' if вар else ''))
            д['inn_v_syryh_company'] = с['inn_raw'] in сырые_инн_компаний
        else:
            д['company'] = компании[с['inn']][:50]
            д['faktov_u_inn'] = len(факты_по_инн[с['inn']])
            # факт есть, но ключ не сошёлся?
            похожие = []
            для_срав = норм(с['obekt'])
            for ф in факты_по_инн[с['inn']]:
                фн = норм(ф['quote'])
                if not фн or not для_срав:
                    continue
                if фн[:40] == для_срав[:40] or фн.startswith(для_срав[:60]) \
                        or для_срав.startswith(фн[:60]):
                    похожие.append(ф)
            if похожие:
                причины.append(
                    'факт ЕСТЬ, ключ не сошёлся (цитата обрезана иначе): '
                    + f'etype={похожие[0]["etype"][:40]}')
                д['fakt_quote'] = похожие[0]['quote'][:110]
                д['fakt_etype'] = похожие[0]['etype'][:60]
                д['fakt_src'] = похожие[0]['src'][:40]
            else:
                # прогнать гейты доливки по исходной строке
                ис = исход_по_ключу.get(с['key']) or []
                if not ис:
                    причины.append('строки НЕТ в исходнике '
                                   '(VAZHNOE-3s-EPB-NASHI-MASHINY.csv)')
                    д['prichina_otseva_v_otseve'] = отсев_по_ключу.get(
                        с['key'], '—')
                else:
                    r = ис[0]
                    д['strok_v_ishodnike'] = len(ис)
                    назв = (r.get('predpriyatie') or '').strip()
                    об = (r.get('obekt') or '').strip()
                    if (r.get('ne_mashina') or '').strip().lower() in (
                            'да', '1', 'true'):
                        причины.append('источник: не машина')
                    if (r.get('nashe_oborudovanie') or '').strip().lower() \
                            not in ('да', '1', 'true'):
                        причины.append('источник: не наше оборудование')
                    ср = среда(назв, об)
                    if ср == 'газ':
                        причины.append('гейт доливки: среда ГАЗ')
                    д['sreda'] = ср or '(не названа)'
                    # марка / справочник
                    if CMK is not None:
                        try:
                            найд = None
                            for сов in re.finditer(
                                    r'\d{0,3}[A-ZА-Яa-zа-я]{1,6}\s?[-–]?\s?'
                                    r'\d[\dA-ZА-Яa-zа-я,./\-]{0,26}', об[:400]):
                                к = сов.group(0).strip(' .,;')
                                if len(к) < 3 or len(к) > 40:
                                    continue
                                if re.match(r'^(?:зав|инв|рег|поз|уч|№|n)\b',
                                            к, re.I):
                                    continue
                                try:
                                    р = CMK.razobrat(к)
                                except Exception:  # noqa: BLE001
                                    р = None
                                if р:
                                    найд = (к, р)
                                    if 'центробежн' in str(
                                            р.get('tip', '')).lower():
                                        break
                            if найд:
                                д['marka'] = найд[0]
                                д['spravochnik_tip'] = str(
                                    найд[1].get('tip'))[:40]
                                д['nash_profil'] = bool(
                                    найд[1].get('nash_profil'))
                                if not найд[1].get('nash_profil') and \
                                        'центробежн' in str(
                                            найд[1].get('tip', '')).lower():
                                    причины.append(
                                        'гейт: марка центробежная, среда '
                                        + str(найд[1].get('sreda')))
                        except Exception as e:  # noqa: BLE001
                            д['marka_oshibka'] = f'{type(e).__name__}'
                    # отбор панели
                    if CM is not None:
                        сост = (r.get('status') or '').strip()
                        истёк = bool(re.search(r'истёк|истек', сост, re.I))
                        факт = {
                            'status': ('экспертиза ЭПБ истекла' if истёк
                                       else 'в работе (заключение ЭПБ действует)'),
                            'model': д.get('marka', ''),
                            'equipment_type':
                                'центробежная (подтверждена перепросом провайдера)',
                            'medium': ср,
                            'evidence': 'перепрос провайдера',
                            'quote': об}
                        try:
                            пр = CM.rejection_reason(факт)
                        except Exception as e:  # noqa: BLE001
                            пр = f'ошибка {type(e).__name__}'
                        д['rejection_reason'] = пр or '(пусто — пускаем)'
                        if пр not in ('', 'ne_centrobezhnaya', None):
                            причины.append(f'отбор панели: {пр}')
                    д['prichina_v_otseve'] = отсев_по_ключу.get(с['key'], '—')
        if not причины:
            причины.append('НЕ ОБЪЯСНЕНО простыми гипотезами')
        д['prichina'] = '; '.join(причины)
        разбор.append(д)

    # --- 6. что потеряется ---
    инн_нет = {с['inn'] for с in нет}
    инн_видно = {с['inn'] for с in видно}
    только_в_хвосте = инн_нет - инн_видно
    без_фактов_вовсе = {и for и in только_в_хвосте
                        if not факты_по_инн.get(и)}
    нет_в_панели = {и for и in инн_нет if и not in компании}
    отчёт['предприятий_в_хвосте'] = len(инн_нет)
    отчёт['из_них_нет_в_company'] = len(нет_в_панели)
    отчёт['предприятий_только_в_хвосте'] = len(только_в_хвосте)
    отчёт['из_них_БЕЗ_единого_факта_в_панели'] = len(без_фактов_вовсе)
    отчёт['инн_без_единого_факта'] = sorted(без_фактов_вовсе)

    # строки, где факт нашёлся нестрого (без метки перепроса) — их замер
    # владельца считал «видно»
    нестрого = [д for д in разбор if 'факт ЕСТЬ' in д['prichina']]
    настоящий_хвост = [д for д in разбор if 'факт ЕСТЬ' not in д['prichina']]
    отчёт['совпало_нестрого_(факт_есть_без_метки)'] = len(нестрого)
    отчёт['НАСТОЯЩИЙ_ХВОСТ'] = len(настоящий_хвост)

    полный = {'svodka': отчёт, 'hvost': разбор}
    п = r'C:\sender\server\HVOST-EPB-wf.json'
    with open(п, 'w', encoding='utf-8') as ф:
        json.dump(полный, ф, ensure_ascii=False, indent=1, default=str)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        import urllib.request
        урл = os.environ.get('DROP_URL',
                             'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/HVOST-EPB-wf.json',
            data=open(п, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        печать_дроп = 'HVOST-EPB-wf.json на дропе'
    except Exception as e:  # noqa: BLE001
        печать_дроп = f'на дроп не ушёл: {e}'

    свод = Counter(д['prichina'].split(';')[0].strip() for д in разбор)
    print('===== СВОД ПРИЧИН =====')
    print(json.dumps(свод.most_common(), ensure_ascii=False, indent=1))
    print('\n===== ХВОСТ КОРОТКО =====')
    for д in разбор:
        print(f"{д['n']:>4} {д['inn']:<13} {д.get('company', д['predpr'])[:26]:<26} "
              f"| {д['prichina'][:78]} | {д['obekt'][:52]}")
    print('\n' + печать_дроп)


if __name__ == '__main__':
    main()
