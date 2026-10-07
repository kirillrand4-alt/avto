# -*- coding: utf-8 -*-
r"""Сбор с нуля, агент 3 — отбор: кандидаты из разбора выдачи (poisk-razbor.jsonl) -> список.

  1. ИНН кандидатов: с сайтов (все ИНН со страниц, первый по частоте — владелец сайта), из каталогов,
     ОГРН -> ИНН (наша база, иначе DaData).
  2. Доход 2025 — ФНС revexp. Порог 1,5 млрд (как в базе КЦ).
  3. Основной ОКВЭД (для тех, кто >= порога): наши базы и кэши (enrich, обзвон, парк, cc-fns,
     kc-okved-fns, poisk-okved) -> DaData (лимит 10k/сутки, при 403/429 ждёт полуночи) и checko через
     прокси (только коды) с другого конца очереди.
  4. Сегмент по основному ОКВЭД (kc_spisok.сегмент); минус запреты панели и ликвидированные.
     С сайта, найденного по сегментному запросу, но с «чужим» основным ОКВЭД (опт, холдинг,
     животноводство, другая пищевка) — на лист «На решение». Сегментные ниже порога — «Ниже порога».
  5. Сайт: свой сайт, где найден ИНН; иначе сайт из нашей базы; иначе поиск xmlriver (лимит).
Выход (fsync): poisk-okved.jsonl (кэш ОКВЭД), poisk-spisok.json -> копии на дроп.
"""
import collections
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
from kc_spisok import сегмент, ЗАКУПКИ  # noqa: E402
from meyer_baza import коды, имя_чисто  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import cc_checko_proxy as CP  # noqa: E402
import enrich_contacts as EC  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ОКВЭД_КЭШ = os.path.join(DIR, 'poisk-okved.jsonl')
ВЫХОД = os.path.join(DIR, 'poisk-spisok.json')
ПОРОГ = 1.5e9
ЛИМИТ_ПОИСКА_САЙТА = 600
# 1-й проход (до полуночи): DaData не ждать (лимит суток выбран), checko сверху и не дольше N минут
НЕ_ЖДАТЬ = os.environ.get('POISK_NE_ZHDAT') == '1'
CHECKO_МИН = int(os.environ.get('POISK_CHECKO_MINUT', '0') or 0)
КЭШ_SUGGEST = os.path.join(DIR, 'poisk-suggest.jsonl')
НА_РЕШЕНИЕ = re.compile(r'^(01\.4|01\.2|10\.|11\.|46\.3|46\.2|70\.10|64\.20)')
_лок = threading.Lock()


def записать_окв(з):
    with _лок:
        with io.open(ОКВЭД_КЭШ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def кандидаты():
    к = {}
    огрн_только = collections.defaultdict(list)
    без_инн = []  # свои сайты без ИНН — юрназвание для DaData suggest

    def добавить(инн, откуда, сайт=None, вес=0, запросы=()):
        x = к.setdefault(инн, {'откуда': [], 'сайты': [], 'запросы': []})
        if откуда not in x['откуда'] and len(x['откуда']) < 6:
            x['откуда'].append(откуда)
        if сайт:
            x['сайты'].append((вес, сайт))
        for q in запросы:
            if len(x['запросы']) < 5 and q not in x['запросы']:
                x['запросы'].append(q)

    for s in io.open(os.path.join(DIR, 'poisk-razbor.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        qq = [q[2] if isinstance(q, (list, tuple)) else q for q in з.get('запросы', [])][:3]
        if з['тип'] == 'сайт' and (len(з.get('инн') or []) >= 4 or len(set(з.get('инн_по_имени') or [])) >= 2):
            # портал/каталог под видом сайта (много чужих ИНН или юрназваний) — только находка, сайт не назначать
            for i, _ in (з.get('инн') or []):
                добавить(i, 'каталог ' + з['домен'], None, 0, qq)
            for i in з.get('инн_по_имени') or []:
                добавить(i, 'каталог ' + з['домен'], None, 0, qq)
            continue
        if з['тип'] == 'сайт':
            инн = з.get('инн') or []
            for j, (i, n) in enumerate(инн):
                добавить(i, 'сайт ' + з['домен'], з['url'], (n if j == 0 else 0) + (100 if j == 0 else 0), qq)
            if not инн:
                for i in з.get('инн_база') or []:
                    добавить(i, 'сайт %s (домен в нашей базе)' % з['домен'], з['url'], 50, qq)
                for i in з.get('инн_по_имени') or []:
                    добавить(i, 'сайт %s (юрназвание с сайта = наша база)' % з['домен'], з['url'], 40, qq)
                if not з.get('инн_база') and not з.get('инн_по_имени') and з.get('юримена'):
                    без_инн.append((з['юримена'][0][0], з['домен'], з['url'], qq))
                if not з.get('инн_база'):
                    for о, _ in з.get('огрн') or []:
                        огрн_только[о].append(('сайт ' + з['домен'], з['url'], qq))
        else:
            for i in (з.get('инн_url') or []) + (з.get('инн') or []):
                добавить(i, 'каталог ' + з.get('домен', ''), None, 0, qq)
            for о in (з.get('огрн_url') or []) + (з.get('огрн') or []):
                огрн_только[о].append(('каталог ' + з.get('домен', ''), None, qq))
    return к, огрн_только, без_инн


def по_имени_dadata(без_инн, к):
    """Сайт без ИНН: DaData suggest/party по юрназванию с сайта; берём, только если ядро названия
    совпало и кандидат один действующий (иначе — ничего, чтобы не приписать чужой ИНН)."""
    tok = EC._read_secret('DADATA_TOKEN')
    прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    n = 0
    кэш = {}
    if os.path.exists(КЭШ_SUGGEST):
        for s_ in io.open(КЭШ_SUGGEST, encoding='utf-8', errors='replace'):
            try:
                x_ = json.loads(s_)
                кэш[x_['юр']] = x_
            except ValueError:
                pass
    for юр, дом, url, qq in без_инн:
        if юр in кэш:
            d = кэш[юр].get('data')
            if d:
                x = к.setdefault(d['inn'], {'откуда': [], 'сайты': [], 'запросы': []})
                x['откуда'].append('сайт %s (юрназвание %s, DaData)' % (дом, юр))
                x['сайты'].append((30, url))
                x['запросы'] += [q for q in qq if q not in x['запросы']][:3]
            continue
        я = re.sub(r'\s+', ' ', re.sub(r'[«»"\'.,]', ' ', юр.split('«', 1)[-1])).strip().lower()
        с = None
        for попытка in range(3):
            try:
                req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                                             data=json.dumps({'query': юр, 'count': 5}).encode(), method='POST', headers={
                                                 'Content-Type': 'application/json', 'Accept': 'application/json',
                                                 'Authorization': 'Token ' + tok})
                с = json.loads(прямой.open(req, timeout=40).read()).get('suggestions') or []
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):  # суточный лимит: ждать смены суток (полночь МСК) и повторить
                    if НЕ_ЖДАТЬ:
                        print('suggest: лимит DaData после %d — добор во 2-м проходе' % n, flush=True)
                        return
                    день = time.strftime('%Y-%m-%d')
                    print('suggest: лимит DaData после %d, жду смены суток' % n, flush=True)
                    while time.strftime('%Y-%m-%d') == день:
                        time.sleep(120)
                    time.sleep(300)
                    continue
                break
            except Exception:  # noqa: BLE001
                time.sleep(3)
        if с is None:
            continue
        n += 1
        годные = [x for x in с if (x.get('data') or {}).get('state', {}).get('status') == 'ACTIVE'
                  and я and я == re.sub(r'\s+', ' ', re.sub(r'[«»"\'.,]', ' ', ((x['data'].get('name') or {}).get('short') or ''))).strip().lower()]
        with _лок:
            with io.open(КЭШ_SUGGEST, 'a', encoding='utf-8') as f_:
                f_.write(json.dumps({'юр': юр, 'data': ({'inn': годные[0]['data']['inn']} if len(годные) == 1 else None)},
                                    ensure_ascii=False) + '\n')
                f_.flush()
                os.fsync(f_.fileno())
        if len(годные) == 1:
            d = годные[0]['data']
            x = к.setdefault(d['inn'], {'откуда': [], 'сайты': [], 'запросы': []})
            x['откуда'].append('сайт %s (юрназвание %s, DaData)' % (дом, юр))
            x['сайты'].append((30, url))
            x['запросы'] += [q for q in qq if q not in x['запросы']][:3]
            записать_окв({'inn': d['inn'], 'источник': 'dadata', 'итог': 'ok', 'оквэд': d.get('okved') or '',
                          'название': (d.get('name') or {}).get('short_with_opf') or '',
                          'регион': ((d.get('address') or {}).get('data') or {}).get('region_with_type') or '',
                          'статус': 'ACTIVE', 'огрн': d.get('ogrn') or ''})
        time.sleep(0.15)
    print('suggest: запросов %d' % n, flush=True)


def доходы(инн):
    д = {}
    z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
    for zi in z.infolist():
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'):
                    continue
                i = v = None
                for ch in el:
                    if 'СведНП' in ch.tag:
                        i = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                    elif 'ДохРасх' in ch.tag:
                        v = ch.get('СумДоход')
                if i in инн and v:
                    try:
                        д[i] = float(v)
                    except ValueError:
                        pass
                el.clear()
    return д


def наши_данные(инн):
    """ОКВЭД/имя/регион/статус/сайт/выручка из наших баз и кэшей."""
    о = {}
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
    for р in c.execute(
            "select t.inn, coalesce(nullif(c.name,''), o.name_short, ''), coalesce(nullif(c.region,''), o.region, ''), "
            "coalesce(nullif(c.site,''), o.sites, ''), coalesce(nullif(c.okved,''), o.okved_main, ''), "
            "coalesce(c.okved_all,'')||' '||coalesce(o.okved_all_codes,''), coalesce(nullif(c.status_egrul,''), o.status, ''), "
            "case when coalesce(c.revenue_rub,0)>0 then c.revenue_rub else o.revenue_rub end, coalesce(c.is_competitor,0) "
            'from t left join companies c on c.inn=t.inn left join obz.obzvon o on o.inn=t.inn'):
        i, имя, рег, сайт, ок, окв, стат, выр, конк = р
        if ок or имя:
            о[i] = {'имя': имя, 'регион': рег, 'сайт': (re.split(r'[\s,;|]+', (сайт or '').strip()) or [''])[0], 'осн': (коды(ок)[:1] or [''])[0],
                    'все': коды(ок, окв), 'статус': стат, 'выр_база': float(выр or 0), 'конкурент': конк,
                    'откуда_окв': 'наша база', 'в_базе': True}
    c.close()
    for п, поле in ((os.path.join(DIR, 'kc-okved-fns.jsonl'), 'оквэд'), (ОКВЭД_КЭШ, 'оквэд')):
        if not os.path.exists(п):
            continue
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            i = з.get('inn')
            if i in инн and з.get('итог') == 'ok' and з.get(поле) and not (о.get(i) or {}).get('осн'):
                имя = з.get('название') or ''
                if з.get('источник') == 'checko':
                    имя = re.split(r',\s|\s[—-]\s', имя)[0]
                о[i] = {'имя': имя, 'регион': з.get('регион') or '', 'сайт': з.get('сайт') or '',
                        'осн': (коды(з[поле])[:1] or [''])[0], 'все': коды(з[поле], ' '.join(з.get('оквэд_все') or [])),
                        'статус': з.get('статус') or '', 'выр_база': 0, 'конкурент': 0,
                        'откуда_окв': з.get('источник') or 'кэш', 'в_базе': False}
    п = os.path.join(DIR, 'cc-fns.json')
    if os.path.exists(п):
        for i, ф in json.load(io.open(п, encoding='utf-8')).items():
            if i in инн and ф.get('оквэд_осн') and not (о.get(i) or {}).get('осн'):
                о[i] = {'имя': ф.get('название') or '', 'регион': ф.get('регион') or '', 'сайт': '',
                        'осн': (коды(ф['оквэд_осн'])[:1] or [''])[0], 'все': коды(ф['оквэд_осн'], ' '.join(ф.get('оквэд_все') or [])),
                        'статус': ф.get('статус') or '', 'выр_база': 0, 'конкурент': 0, 'откуда_окв': 'таблица CC', 'в_базе': True}
    return о


def добрать_оквэд(нужно, доход):
    """DaData сверху (по убыванию дохода), checko снизу; DaData при 403/429 ждёт смены суток."""
    очередь = sorted(нужно, key=lambda i: -доход.get(i, 0))
    гр = {'верх': 0, 'низ': len(очередь)}
    гл = threading.Lock()
    сост = {'dadata_стоп_дата': '', 'dadata': 0, 'checko': 0}

    def взять(сверху):
        with гл:
            if гр['верх'] >= гр['низ']:
                return None
            if сверху:
                гр['верх'] += 1
                return очередь[гр['верх'] - 1]
            гр['низ'] -= 1
            return очередь[гр['низ']]

    tok = EC._read_secret('DADATA_TOKEN')
    прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def dadata():
        while True:
            if сост.get('dadata_выкл'):
                return
            if сост['dadata_стоп_дата'] == time.strftime('%Y-%m-%d'):
                if гр['верх'] >= гр['низ']:
                    return
                time.sleep(120)
                continue
            i = взять(True)
            if i is None:
                return
            з = {'inn': i, 'источник': 'dadata'}
            try:
                req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                             data=json.dumps({'query': i}).encode(), method='POST', headers={
                                                 'Content-Type': 'application/json', 'Accept': 'application/json',
                                                 'Authorization': 'Token ' + tok})
                с = json.loads(прямой.open(req, timeout=40).read()).get('suggestions') or []
                if с:
                    d = с[0]['data']
                    а = (d.get('address') or {}).get('data') or {}
                    з.update({'итог': 'ok', 'оквэд': d.get('okved') or '', 'название': (d.get('name') or {}).get('short_with_opf') or с[0].get('value'),
                              'регион': а.get('region_with_type') or '', 'статус': (d.get('state') or {}).get('status') or '',
                              'огрн': d.get('ogrn') or ''})
                else:
                    з['итог'] = 'не найден'
                сост['dadata'] += 1
            except urllib.error.HTTPError as e:
                з.update({'итог': 'ошибка', 'ошибка': 'HTTP %s' % e.code})
                if e.code in (403, 429):
                    if НЕ_ЖДАТЬ:
                        сост['dadata_выкл'] = True
                    сост['dadata_стоп_дата'] = time.strftime('%Y-%m-%d')  # лимит суток; вернуть ИНН нельзя — подберёт checko/повтор
                    with гл:
                        очередь.append(i)
                        гр['низ'] += 1
                    continue
            except Exception as e:  # noqa: BLE001
                з.update({'итог': 'ошибка', 'ошибка': repr(e)[:80]})
            записать_окв(з)
            time.sleep(0.2)

    прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    прокси = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]

    t_старт = time.time()

    def checko(п):
        while True:
            if CHECKO_МИН and time.time() - t_старт > CHECKO_МИН * 60:
                return
            i = взять(НЕ_ЖДАТЬ)  # в 1-м проходе DaData нет — checko идёт с самых крупных
            if i is None:
                return
            з = {'inn': i, 'источник': 'checko'}
            код, html = п.get('https://checko.ru/search?query=%s' % i)
            if код != 200:
                з.update({'итог': 'ошибка', 'ошибка': str(код)})
            else:
                т = CP.текст(html)
                ок = CP.окведы(т)
                заг = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
                з.update({'итог': 'ok' if ок else 'нет оквэд', 'оквэд': ок[0] if ок else '', 'оквэд_все': ок[:40],
                          'название': re.sub(r'\s+', ' ', заг.group(1)).strip()[:150] if заг else '',
                          'статус': 'ликвидирована' if re.search(r'ликвидирован|прекратил[ао]? деятельность', т[:6000], re.I) else ''})
                сост['checko'] += 1
            записать_окв(з)

    нити = [threading.Thread(target=dadata) for _ in range(6)] + [threading.Thread(target=checko, args=(п,)) for п in прокси]
    for н in нити:
        н.start()
    t0 = time.time()
    while any(н.is_alive() for н in нити):
        time.sleep(60)
        print('оквэд: %d мин, dadata %d, checko %d, осталось %d %s' % ((time.time() - t0) / 60, сост['dadata'], сост['checko'],
              гр['низ'] - гр['верх'], ('DaData ждёт суток' if сост['dadata_стоп_дата'] else '')), flush=True)


def main():
    к, огрн_только, без_инн = кандидаты()
    print('свои сайты без ИНН (юрназвание -> DaData)', len(без_инн), flush=True)
    по_имени_dadata(без_инн, к)
    print('кандидатов ИНН', len(к), 'ОГРН без ИНН', len(огрн_только), flush=True)
    # ОГРН -> ИНН по нашей базе (если есть колонка), остальные — DaData findById принимает ОГРН
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    кол = [r[1] for r in c.execute('pragma table_info(companies)')]
    if 'ogrn' in кол:
        for о, i in c.execute('select ogrn, inn from companies where ogrn in (%s)' % ','.join('?' * len(огрн_только)), list(огрн_только)) if огрн_только else []:
            for откуда, сайт, qq in огрн_только.pop(о, []):
                x = к.setdefault(str(i), {'откуда': [], 'сайты': [], 'запросы': []})
                x['откуда'].append(откуда)
                if сайт:
                    x['сайты'].append((10, сайт))
    c.close()
    # ОГРН, не найденные в базе, через доход не отсечь (нужен ИНН) — DaData по ОГРН, только с сайтов (их мало)
    tok = EC._read_secret('DADATA_TOKEN')
    прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for о, вх in list(огрн_только.items()):
        if not any(сайт for _, сайт, _ in вх):
            continue
        try:
            req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                         data=json.dumps({'query': о}).encode(), method='POST', headers={
                                             'Content-Type': 'application/json', 'Accept': 'application/json',
                                             'Authorization': 'Token ' + tok})
            с = json.loads(прямой.open(req, timeout=40).read()).get('suggestions') or []
            if с:
                i = с[0]['data'].get('inn')
                x = к.setdefault(i, {'откуда': [], 'сайты': [], 'запросы': []})
                for откуда, сайт, qq in вх:
                    x['откуда'].append(откуда)
                    if сайт:
                        x['сайты'].append((10, сайт))
        except Exception:  # noqa: BLE001
            break  # лимит DaData — не страшно, это добор
    доход = доходы(set(к))
    из_фнс = set(доход)
    print('с доходом ФНС', len(доход), 'из них >= порога', sum(1 for v in доход.values() if v >= ПОРОГ), flush=True)
    наши = наши_данные(set(к))
    for i, о in наши.items():  # выручка из базы — если в ФНС нет (крупнейшие налогоплательщики)
        if i not in доход and о.get('выр_база'):
            доход[i] = о['выр_база']
    нужно = [i for i in к if доход.get(i, 0) >= ПОРОГ and not (наши.get(i) or {}).get('осн')]
    print('нужно ОКВЭД (>= порога, нет у нас)', len(нужно), flush=True)
    if нужно:
        добрать_оквэд(нужно, доход)
        наши.update({i: v for i, v in наши_данные(set(нужно)).items() if v.get('осн')})
    # запреты панели
    c = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=60)
    т = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name like '%suppress%'")][0]
    кк = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
    зап = {}
    for r in c.execute("select * from %s where scope='inn'" % т):
        x = dict(zip(кк, r))
        rs, src = x.get('reason') or '', x.get('source') or ''
        зап[str(x['value'])] = ('идёт сделка (панель)' if rs == 'deal_in_progress' or 'сделка' in src.lower() else
                                'конкурент (панель)' if 'competitor' in rs or 'конкурент' in rs else '%s (панель)' % rs)
    c.close()
    итог, снято, ниже, на_решение = {}, {}, {}, {}
    for i, x in к.items():
        о = наши.get(i) or {}
        осн = о.get('осн') or ''
        с = сегмент(осн, о.get('все') or [осн]) if осн else ''
        выр = доход.get(i, 0)
        сайты = sorted(x['сайты'], key=lambda t: -t[0])
        сайт = сайты[0][1] if сайты else (о.get('сайт') or '')
        запись = {'inn': i, 'имя': имя_чисто(о.get('имя') or ''), 'регион': о.get('регион') or '', 'сайт': сайт,
                  'осн': осн, 'все': о.get('все') or [], 'сегм': с, 'выручка': выр,
                  'выручка_откуда': 'ФНС (доход 2025)' if i in из_фнс else ('наша база' if выр else ''),
                  'откуда': 'поиск: ' + '; '.join(x['откуда'][:3]), 'запросы': x['запросы'][:3],
                  'в_нашей_базе': 'да' if о.get('в_базе') else 'нет', 'огрн': ''}
        if not с:
            if выр >= ПОРОГ and осн and НА_РЕШЕНИЕ.match(осн) and any(о2.startswith('сайт') for о2 in x['откуда']):
                на_решение[i] = dict(запись, причина='сайт найден по запросу сегмента, но основной ОКВЭД %s' % осн)
            continue
        if re.search(r'LIQUIDAT|BANKRUPT|ликвид|банкрот', о.get('статус') or '', re.I):
            снято[i] = dict(запись, причина='ликвидирована/банкрот (%s)' % о.get('статус'))
            continue
        if о.get('конкурент'):
            снято[i] = dict(запись, причина='конкурент (наша база)')
            continue
        if i in зап:
            снято[i] = dict(запись, причина=зап[i])
            continue
        if выр < ПОРОГ:
            ниже[i] = запись
            continue
        итог[i] = запись
    # сайт для тех, у кого его нет: поиск xmlriver (проверка «чей сайт» — потом, kc_audit)
    без = sorted((к2 for к2 in итог.values() if not к2['сайт']), key=lambda к2: -к2['выручка'])[:ЛИМИТ_ПОИСКА_САЙТА]
    for к2 in без:
        try:
            рег = re.sub(r'\b(обл|область|край|респ|республика|г)\b\.?', ' ', к2['регион']).strip()
            сайт, ист, _ = EC.find_site_via_xmlriver({'name': к2['имя'], 'city': рег})
            if сайт:
                к2['сайт'], к2['сайт_откуда'] = сайт, 'поиск по названию (%s)' % ист
            elif 'закончились средства' in (ист or ''):
                break
        except Exception:  # noqa: BLE001
            pass
    # страницы-источники наших контактов (свой домен и закупки) — как в kc_spisok
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert into t values (?)', [(i,) for i in итог])
    for i, url in c.execute("select inn, source_url from people where inn in (select inn from t) and coalesce(source_url,'')<>'' "
                            "union select inn, source_url from phone_contacts where inn in (select inn from t) and coalesce(source_url,'')<>''"):
        к2 = итог[str(i)]
        if ЗАКУПКИ.search(url):
            к2.setdefault('закупки_базы', []).append(url)
        elif к2['сайт'] and MN.домен(url) == MN.домен(к2['сайт']):
            к2.setdefault('страницы_базы', []).append(url)
    c.close()
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        json.dump({'компании': итог, 'снято': снято, 'ниже_порога': ниже, 'на_решение': на_решение}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'poisk-spisok.json'))
    if os.path.exists(ОКВЭД_КЭШ):
        shutil.copyfile(ОКВЭД_КЭШ, os.path.join(ДРОП, 'poisk-okved.jsonl'))
    сч = collections.Counter(к2['сегм'] for к2 in итог.values())
    print('готово', json.dumps({'компаний': len(итог), 'по_сегментам': dict(сч), 'снято': len(снято), 'ниже_порога': len(ниже),
                                'на_решение': len(на_решение), 'с_сайтом': sum(1 for к2 in итог.values() if к2['сайт']),
                                'новых_не_в_базе': sum(1 for к2 in итог.values() if к2['в_нашей_базе'] == 'нет')},
                               ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
