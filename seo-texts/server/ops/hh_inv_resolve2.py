# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, шаг 2б (вторая редакция): РАБОТОДАТЕЛЬ -> ИНН, с разбором.

Первая редакция звала news_scan.dadata_suggest и брала лучший ответ. Проверка
глазами показала ДВА способа промахнуться, и оба системные, а не случайные:

1. ПРОФСОЮЗ ВМЕСТО ЗАВОДА. У dadata в выдаче по «Новокуйбышевский
   нефтеперерабатывающий завод» первым идёт «ОППО АО "НК НПЗ"
   НЕФТЕГАЗСТРОЙПРОФСОЮЗА РОССИИ» — первичная профсоюзная организация. Имя
   содержит имя завода целиком, поэтому матч-скор у неё максимальный, и лид
   уезжал профсоюзу. То же самое случилось с «Восточно-Сибирской нефтегазовой
   компанией». Лечится ДО скоринга: профсоюзные, партийные и садоводческие
   формы выбрасываем из кандидатов, а не выбираем среди них лучшую.

2. ГРУППОВОЙ ПОРТАЛ ВМЕСТО СВОЕГО САЙТА. hh у «РН-Ванкор», «РН-Комсомольский
   НПЗ» и «Восточно-Сибирской нефтегазовой» указывает ОДИН И ТОТ ЖЕ сайт
   rosneft.ru, и ИНН с него — это ПАО «НК «Роснефть», а не дочернее общество.
   Признак портала дешёвый и честный: домен встречается у ДВУХ И БОЛЕЕ разных
   работодателей нашей же выборки. Такой домен доказательством не считаем.

Здесь же собираем то, чего в первой редакции не было и без чего рубеж не
закрыть: ГОРОД из адреса ЕГРЮЛ (сравнивать с городом вакансии напрямую) и
признак ТОЧНОГО совпадения имени работодателя с наименованием из ЕГРЮЛ без
ОПФ — это ровно тот критерий, который принят в hh_страница_наша.
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402  (_name_variants, _match_score — обкатаны)

DROP = r'C:\seostat\drop'
STORE = os.path.join(DROP, 'drop-storage')
VAC = os.path.join(STORE, 'hh_inv_vacancies.jsonl')
STREAM = os.path.join(DROP, 'hh_inv_resolve2_stream.jsonl')

SUGGEST = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'

# Формы, которые НИКОГДА не являются работодателем-заводом, но носят его имя.
_НЕ_КОМПАНИЯ = re.compile(
    r'профсоюз|первичная\s+профсоюзная|\bППО\b|\bОППО\b'
    r'|садовод|некоммерческое\s+партнёрств|товарищество\s+собственник'
    r'|политическ|религиозн|\bТСЖ\b|\bСНТ\b|\bГСК\b', re.I)

_ЛОК = threading.Lock()


def _норм(s):
    return re.sub(r'[^0-9a-zа-яё]+', '', (s or '').lower())


_ОПФ = re.compile(
    r'^(?:общество\s+с\s+ограниченной\s+ответственностью|акционерное\s+общество'
    r'|публичное\s+акционерное\s+общество|непубличное\s+акционерное\s+общество'
    r'|закрытое\s+акционерное\s+общество|открытое\s+акционерное\s+общество'
    r'|ооо|оао|зао|пао|ао|ип|нао|гуп|муп|фгуп|фгбу|мбу|гбуз|фку|пк|нпо|нпп)\s+',
    re.I)


def _без_опф(s):
    s = re.sub(r'[«»"„“]', ' ', (s or '')).strip()
    prev = None
    while prev != s:
        prev = s
        s = _ОПФ.sub('', s).strip()
    return s


def _чистое_имя(nm):
    """hh пишет «Бренд, длинное описание» — для dadata годится только «Бренд».

    Отдельный случай, найденный проверкой глазами: работодатель САМ называет
    юрлицо в скобках — «Bombbar (ООО Фитнес Фуд)», «ГК КриоФрост (ООО
    ТехноФрост)», «Группа компаний ВЕКТОР (ООО Арбелос)». Там в скобках стоит
    ровно то, что нужно искать, а снаружи — бренд, под которым юрлица в ЕГРЮЛ
    нет вовсе. Раньше искали по бренду, не находили ничего и падали на сайт —
    а сайт у бренда общий с другим юрлицом группы.
    """
    nm = (nm or '').strip()
    nm = re.sub(r'\s*\((?:вакансии|карьера)[^)]*\)\s*$', '', nm, flags=re.I)
    m = re.search(r'\((?:ООО|АО|ЗАО|ПАО|ОАО|НАО|ГУП|МУП|ФГУП|ИП)\s+([^)]{3,60})\)',
                  nm, re.I)
    if m:
        return m.group(1).strip()
    if ',' in nm:
        голова = nm.split(',')[0].strip()
        if len(голова) >= 4:
            return голова
    return nm


def _suggest(q, tok, count=7):
    body = json.dumps({'query': q, 'count': count}).encode()
    req = urllib.request.Request(SUGGEST, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': f'Token {tok}'})
    for att in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=25).read()
                              ).get('suggestions') or []
        except urllib.error.HTTPError as he:
            if he.code in (429, 500, 502, 503):
                time.sleep(2.0 * (att + 1))
                continue
            return []
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (att + 1))
    return []


def кандидаты(имя, tok):
    """Все варианты имени -> кандидаты, БЕЗ профсоюзов, отсортированы по скору."""
    видели, из = set(), []
    for v in NS._name_variants(имя):
        for s in _suggest(v, tok):
            val = s.get('value') or ''
            d = s.get('data') or {}
            inn = d.get('inn') or ''
            if not inn or inn in видели:
                continue
            if _НЕ_КОМПАНИЯ.search(val):
                continue        # профсоюз/СНТ/ТСЖ носит имя завода, но не завод
            видели.add(inn)
            adr = (d.get('address') or {}).get('data') or {}
            из.append({
                'inn': inn, 'name': val, 'okved': d.get('okved') or '',
                'region': adr.get('region') or '',
                'city': adr.get('city') or adr.get('settlement')
                or adr.get('area') or '',
                'status': (d.get('state') or {}).get('status') or '',
                'branch': (d.get('branch_type') or ''),
                'score': NS._match_score(имя, val),
                'точное': _норм(_без_опф(val)) == _норм(_без_опф(имя)),
                'egrul_emails': [e.get('value') for e in (d.get('emails') or [])
                                 if isinstance(e, dict) and e.get('value')][:2],
            })
        if any(c['точное'] for c in из):
            break               # точное совпадение найдено — не жжём лимит
    из.sort(key=lambda c: (c['точное'], c['status'] == 'ACTIVE', c['score']),
            reverse=True)
    return из[:5]


def работодатели(path=VAC):
    из = {}
    with open(path, encoding='utf-8') as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not (r.get('employer') or '').strip():
                continue
            k = r.get('employer_id') or ('nm:' + r['employer'])
            e = из.setdefault(k, {
                'employer_id': r.get('employer_id') or '', 'employer': r['employer'],
                'employer_url': r.get('employer_url') or '', 'sites': set(),
                'areas': {}, 'vacancies': [], 'queries': set(), 'fields': set(),
                'n': 0})
            if r.get('employer_site'):
                e['sites'].add(r['employer_site'])
            if r.get('area'):
                e['areas'][r['area']] = e['areas'].get(r['area'], 0) + 1
            if r.get('city'):
                e.setdefault('cities', {})
                e['cities'][r['city']] = e['cities'].get(r['city'], 0) + 1
            if len(e['vacancies']) < 8:
                e['vacancies'].append({'name': r.get('vacancy'),
                                       'url': r.get('vacancy_url'),
                                       'published': r.get('published')})
            e['queries'].add(r.get('query') or '')
            e['fields'].add(r.get('field') or '')
            e['n'] += 1
    for e in из.values():
        e['sites'] = sorted(e['sites'])
        e['queries'] = sorted(e['queries'])
        e['fields'] = sorted(e['fields'])
        e.setdefault('cities', {})
    return из


def main():
    бюджет = 400.0
    for i, a in enumerate(sys.argv):
        if a == '--budget' and i + 1 < len(sys.argv):
            бюджет = float(sys.argv[i + 1])
    t0 = time.time()
    tok = os.environ.get('DADATA_TOKEN', '')
    if not tok:
        print('НЕТ DADATA_TOKEN', flush=True)
        return
    из = работодатели()
    # --recheck: перепройти тех, у кого ИМЯ ЗАПРОСА изменилось после правки
    # _чистое_имя. Без этого правка молча не действует на уже пройденных.
    recheck = '--recheck' in sys.argv
    сделано = set()
    if os.path.exists(STREAM):
        for ln in open(STREAM, encoding='utf-8'):
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if recheck and r['key'] in из and \
                    r.get('query_name') != _чистое_имя(из[r['key']]['employer']):
                continue          # имя поменялось — пойдём ещё раз
            сделано.add(r['key'])
    надо = [k for k in из if k not in сделано]
    print(f'=== СТАРТ resolve2: работодателей {len(из)}, сделано {len(сделано)}, '
          f'к резолву {len(надо)}, бюджет {бюджет:.0f}с ===', flush=True)
    fh = open(STREAM, 'a', encoding='utf-8')
    сч = {'точное': 0, 'скор2': 0, 'скор1': 0, 'пусто': 0, 'сделано': 0}

    def один(k):
        if time.time() - t0 > бюджет:
            return
        e = из[k]
        имя = _чистое_имя(e['employer'])
        try:
            cand = кандидаты(имя, tok)
        except Exception as ex:  # noqa: BLE001
            cand = []
            print(f'  сбой на {имя}: {type(ex).__name__}', flush=True)
        rec = dict(e)
        rec['key'] = k
        rec['query_name'] = имя
        rec['кандидаты'] = cand
        rec['ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        with _ЛОК:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            fh.flush()
            os.fsync(fh.fileno())
            сч['сделано'] += 1
            if not cand:
                сч['пусто'] += 1
            elif cand[0]['точное']:
                сч['точное'] += 1
            elif cand[0]['score'] >= 2:
                сч['скор2'] += 1
            else:
                сч['скор1'] += 1
            if сч['сделано'] % 60 == 0:
                print(f'  {сч["сделано"]}/{len(надо)} точных={сч["точное"]} '
                      f'скор2={сч["скор2"]} скор1={сч["скор1"]} '
                      f'пусто={сч["пусто"]}', flush=True)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(один, надо))
    fh.close()
    print(f'=== ИТОГ resolve2: за прогон {сч["сделано"]}, точных {сч["точное"]}, '
          f'скор>=2 {сч["скор2"]}, скор1 {сч["скор1"]}, пусто {сч["пусто"]} ===',
          flush=True)
    print(f'ВСЕГО в потоке: {len(сделано) + сч["сделано"]} из {len(из)}', flush=True)


if __name__ == '__main__':
    main()
    os._exit(0)
