# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, шаг 3 (вторая редакция): свести доказательства, померить, записать.

Рубеж принадлежности закрыт по умолчанию. Принимаем ИНН только по одному из
доказательств, каждое из которых пережило проверку глазами:

  A. ИНН прочитан на СОБСТВЕННОМ сайте работодателя. «Собственный» — значит
     домен встречается у ОДНОГО работодателя нашей выборки. Домен, общий для
     нескольких (rosneft.ru у «РН-Ванкора», «РН-Комсомольского НПЗ» и
     «Восточно-Сибирской нефтегазовой»), — это портал группы, и ИНН с него
     принадлежит материнской компании, а не тому, кто нанимает.
  B. Наименование в ЕГРЮЛ совпало с названием работодателя ПОЛНОСТЬЮ (после
     снятия ОПФ и знаков). Это тот же критерий, что в hh_страница_наша.
     Если полных совпадений НЕСКОЛЬКО — это тёзки, и тогда решает город или
     регион; не разрешилось — ИНН не пишем.
  C. Совпало два и более содержательных токена имени И сошёлся город/регион.

Всё остальное — лид БЕЗ ИНН. Отдельно считаем, сколько таких: пропуск виден,
а чужой ИНН в базе не виден и стоит дороже.

Новизна считается против ОБЕИХ баз: выгрузка обзвона (master-base.sqlite,
162 440 юрлиц) и enrich.db (9 668 обогащённых, среди них есть компании,
которых в выгрузке нет вовсе).
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402
import news_scan as NS  # noqa: E402  (_match_score)

FINDBYID = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'

DROP = r'C:\seostat\drop'
STORE = os.path.join(DROP, 'drop-storage')
RESOLVE = os.path.join(DROP, 'hh_inv_resolve2_stream.jsonl')
MERGED = os.path.join(DROP, 'hh_inv_merged2_stream.jsonl')
MASTER = os.path.join(STORE, 'master-base.sqlite')

_ХОЛОД = re.compile(r'холодильн', re.I)
_ПЕРЕДВИЖ = re.compile(r'передвижн|мобильн|с двигателем внутреннего', re.I)


def _dom(u):
    u = (u or '').strip()
    if not u:
        return ''
    if not re.match(r'^https?://', u, re.I):
        u = 'http://' + u
    try:
        h = urllib.parse.urlparse(u).netloc.lower().split(':')[0]
    except Exception:  # noqa: BLE001
        return ''
    return h[4:] if h.startswith('www.') else h


def _site_map():
    m = {}
    for f in ('hh_site_inn.jsonl', 'hh_site_inn2.jsonl'):
        p = os.path.join(STORE, f)
        if not os.path.exists(p):
            continue
        for ln in open(p, encoding='utf-8'):
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if r.get('inn') and r.get('host'):
                m[r['host']] = {'inn': r['inn'], 'url': r.get('url') or ''}
    return m


def _норм(s):
    return re.sub(r'[^0-9a-zа-яё]+', '', (s or '').lower())


_ОПФ = re.compile(
    r'^(?:общество\s+с\s+ограниченной\s+ответственностью|акционерное\s+общество'
    r'|публичное\s+акционерное\s+общество|непубличное\s+акционерное\s+общество'
    r'|закрытое\s+акционерное\s+общество|открытое\s+акционерное\s+общество'
    r'|ооо|оао|зао|пао|ао|ип|нао|гуп|муп|фгуп|фгбу|пк|нпо|нпп)\s+', re.I)


def _без_опф(s):
    s = re.sub(r'[«»"„“]', ' ', (s or '')).strip()
    prev = None
    while prev != s:
        prev = s
        s = _ОПФ.sub('', s).strip()
    return s


def _чистое_имя(nm):
    nm = (nm or '').strip()
    nm = re.sub(r'\s*\((?:вакансии|карьера)[^)]*\)\s*$', '', nm, flags=re.I)
    m = re.search(r'\((?:ООО|АО|ЗАО|ПАО|ОАО|НАО|ГУП|МУП|ФГУП|ИП)\s+([^)]{3,60})\)',
                  nm, re.I)
    if m:
        return m.group(1).strip()
    if ',' in nm:
        г = nm.split(',')[0].strip()
        if len(г) >= 4:
            return г
    return nm


def совместимо(имя_hh, имя_егрюл):
    """Одна ли это компания по НАЗВАНИЮ — для проверки привязки по сайту/домену.

    Понадобилось после разбора глазами. hh-работодатель «Группа ПРОДО» указывает
    сайт prodo.ru, а в базе обзвона этот домен закреплён за АО «ПРОДО ЗЕРНО
    ЭЛЕВАТОР» — дочерним элеватором. Привязка по домену молча отдала лид не
    тому юрлицу группы, ровно как rosneft.ru отдавал дочерние общества
    материнской компании. Домен доказывает принадлежность САЙТА, а не то, что
    нанимает именно это юрлицо, поэтому имя обязано сойтись тоже.
    """
    a, b = _норм(_без_опф(_чистое_имя(имя_hh))), _норм(_без_опф(имя_егрюл or ''))
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 5 and a in b:
        return True
    if len(b) >= 5 and b in a:
        return True
    return NS._match_score(_чистое_имя(имя_hh), имя_егрюл or '') >= 2


def main():
    apply = '--apply' in sys.argv
    t0 = time.time()
    print(f'=== СТАРТ merge2 (apply={apply}) ===', flush=True)

    # Поток дописывается, и после --recheck в нём ДВЕ записи на один ключ.
    # Берём последнюю: иначе решение принимается по устаревшему разбору имени.
    _по = {}
    for l in open(RESOLVE, encoding='utf-8'):
        try:
            r = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        _по[r['key']] = r
    рез = list(_по.values())
    сайты = _site_map()
    классы = {}
    p_cls = os.path.join(STORE, 'hh_inv_classes.json')
    if os.path.exists(p_cls):
        классы = json.load(open(p_cls, encoding='utf-8'))
        # провайдер изредка возвращает класс с опечаткой («конечний») — приводим
        # к канону, иначе один работодатель молча выпадет из подсчёта лидов
        канон = {'конечний потребитель': 'конечный потребитель'}
        for v in классы.values():
            v['класс'] = канон.get(v.get('класс'), v.get('класс'))

    # СКОЛЬКО РАЗНЫХ работодателей делят домен: 2+ значит портал группы
    польз = Counter()
    for r in рез:
        for h in {_dom(s) for s in (r.get('sites') or [])}:
            if h:
                польз[h] += 1
    порталы = {h for h, n in польз.items() if n > 1}
    print(f'работодателей {len(рез)}; сайтов с ИНН {len(сайты)}; '
          f'доменов-порталов (2+ работодателя) {len(порталы)}; '
          f'классов {len(классы)}', flush=True)

    mcx = sqlite3.connect(f'file:{MASTER}?mode=ro', uri=True)
    вбазе, домены, город2рег = {}, {}, {}
    for адрес, рег in mcx.execute(
            "SELECT address, region FROM master WHERE COALESCE(address,'')!=''"):
        if not рег:
            continue
        for m in re.finditer(
                r'(?:^|,)\s*(?:г\.?|город|пгт\.?|с\.|село|рп\.?|п\.|посёлок|'
                r'поселок|д\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{2,28})', адрес or ''):
            г = m.group(1).strip().lower()
            if len(г) >= 3:
                город2рег.setdefault(г, set()).add(рег)
    for inn, nm, div, okv, reg, rev, site, pmax, eq, comp in mcx.execute(
            'SELECT inn,name,division,okved,region,revenue_rub,site,priority_max,'
            'equipment,is_competitor FROM master'):
        i = str(inn or '').strip()
        if not i:
            continue
        вбазе[i] = {'name': nm, 'division': div, 'okved': okv, 'region': reg,
                    'revenue_rub': rev, 'site': site, 'priority_max': pmax,
                    'equipment': eq, 'is_competitor': comp}
        d = _dom(site)
        if d:
            домены.setdefault(d, i)
    mcx.close()
    print(f'база обзвона {len(вбазе)} ИНН, с сайтом {len(домены)}, '
          f'справочник городов {len(город2рег)}', flush=True)

    db = EDB.EnrichDB()
    в_enrich = {r[0] for r in db.cx.execute('SELECT inn FROM companies')}
    print(f'enrich.db {len(в_enrich)} компаний', flush=True)

    _tok = os.environ.get('DADATA_TOKEN', '')
    _кэш_имён = {}

    def егрюл_имя(inn):
        """Наименование по ИНН — чтобы проверить, ЧЕЙ ИНН мы прочитали на сайте."""
        if not inn:
            return ''
        if inn in _кэш_имён:
            return _кэш_имён[inn]
        v = (вбазе.get(inn) or {}).get('name') or ''
        if not v and _tok:
            try:
                req = urllib.request.Request(
                    FINDBYID, data=json.dumps({'query': inn}).encode(),
                    method='POST', headers={'Content-Type': 'application/json',
                    'Accept': 'application/json', 'Authorization': f'Token {_tok}'})
                sg = json.loads(urllib.request.urlopen(req, timeout=25).read()
                                ).get('suggestions') or []
                v = (sg[0].get('value') if sg else '') or ''
            except Exception:  # noqa: BLE001
                v = ''
        _кэш_имён[inn] = v
        return v

    def место_сошлось(cand, города):
        """Город ЕГРЮЛ против городов вакансий — прямо, потом через справочник."""
        c = _норм(cand.get('city'))
        for г in города:
            гн = _норм(re.sub(r'\s*\(.*', '', г or ''))
            if c and гн and (c == гн or (len(c) > 4 and c in гн) or
                             (len(гн) > 4 and гн in c)):
                return True
        r = _норм(re.sub(r'(область|край|республика|автономный округ|округ)', ' ',
                         (cand.get('region') or '').lower()))
        if not r:
            return False
        for г in города:
            гн = re.sub(r'\s*\(.*', '', (г or '')).strip().lower()
            if len(r) >= 4 and r[:6] in _норм(гн):
                return True
            for рг in город2рег.get(гн, ()):
                a = _норм(re.sub(r'(область|край|республика|автономный округ|'
                                 r'округ)', ' ', (рг or '').lower()))
                if a and (a[:7] == r[:7] or a in r or r in a):
                    return True
        return False

    fh = open(MERGED, 'w', encoding='utf-8')
    сч = Counter()
    строки = []
    for r in рез:
        сч['всего'] += 1
        города = list((r.get('areas') or {}).keys()) + list((r.get('cities') or {}).keys())
        хосты = [h for h in ({_dom(s) for s in (r.get('sites') or [])}) if h]
        свои = [h for h in хосты if h not in порталы]
        cand = r.get('кандидаты') or []
        точные = [c for c in cand if c.get('точное')]
        активные_точные = [c for c in точные if c.get('status') == 'ACTIVE'] or точные

        site_inn, site_url = '', ''
        for h in свои:
            if h in сайты:
                site_inn, site_url = сайты[h]['inn'], сайты[h]['url']
                break
        dom_inn = next((домены[h] for h in свои if h in домены), '')
        # ИМЯ ВЛАДЕЛЬЦА ИНН ОБЯЗАНО СОЙТИСЬ с именем работодателя, иначе сайт —
        # это портал бренда или группы, а ИНН на нём чужой.
        if site_inn and not совместимо(r['employer'], егрюл_имя(site_inn)):
            сч['отказ:сайт_чужое_юрлицо'] += 1
            site_inn, site_url = '', ''
        if dom_inn and not совместимо(r['employer'], егрюл_имя(dom_inn)):
            сч['отказ:домен_чужое_юрлицо'] += 1
            dom_inn = ''

        inn, доказ, качество, замечание = '', '', '', ''
        if site_inn:
            inn = site_inn
            доказ = f'ИНН прочитан на собственном сайте работодателя: {site_url}'
            качество = 'сильное'
            сч['док:сайт'] += 1
            прочие = {c['inn'] for c in активные_точные}
            if прочие and site_inn not in прочие:
                замечание = ('ЕГРЮЛ по точному названию даёт другой ИНН: '
                             + ', '.join(sorted(прочие))[:60])
                сч['расхождение'] += 1
        elif len(активные_точные) == 1:
            c = активные_точные[0]
            inn, качество = c['inn'], 'сильное'
            доказ = f'наименование ЕГРЮЛ совпало полностью: {c["name"]}'
            сч['док:имя_точное'] += 1
        elif len(активные_точные) > 1:
            # тёзки: «Теплоэнерго» есть в каждом втором регионе
            под = [c for c in активные_точные if место_сошлось(c, города)]
            if len(под) == 1:
                inn, качество = под[0]['inn'], 'сильное'
                доказ = (f'наименование ЕГРЮЛ совпало полностью и место сошлось: '
                         f'{под[0]["name"]}, {под[0].get("city") or под[0].get("region")}')
                сч['док:имя_точное+место'] += 1
            else:
                доказ = (f'полных тёзок {len(активные_точные)}, местом не '
                         f'различаются — ИНН не приклеиваем')
                сч['отказ:тёзки'] += 1
        elif dom_inn:
            inn, качество = dom_inn, 'сильное'
            доказ = 'домен собственного сайта совпал с компанией базы обзвона'
            сч['док:домен'] += 1
        else:
            силь = [c for c in cand if c.get('score', 0) >= 2
                    and c.get('status') == 'ACTIVE' and место_сошлось(c, города)]
            if len(силь) == 1:
                inn, качество = силь[0]['inn'], 'среднее'
                доказ = (f'совпало {силь[0]["score"]} токена названия + место: '
                         f'{силь[0]["name"]}')
                сч['док:токены+место'] += 1
            elif cand:
                доказ = (f'кандидат есть ({cand[0]["name"][:40]}, скор '
                         f'{cand[0].get("score")}), но ни название целиком, ни '
                         f'место не подтвердились')
                сч['отказ:слабо'] += 1
            else:
                доказ = 'dadata не нашла юрлицо с таким названием'
                сч['отказ:пусто'] += 1

        m = вбазе.get(inn) if inn else None
        есть_e = bool(inn and inn in в_enrich)
        if inn:
            сч['с_инн'] += 1
            if m:
                сч['в_базе_обзвона'] += 1
            if есть_e:
                сч['в_enrich'] += 1
            if m or есть_e:
                сч['в_любой_базе'] += 1
            else:
                сч['НОВЫХ'] += 1
        else:
            сч['без_инн'] += 1

        назв = [v.get('name') or '' for v in (r.get('vacancies') or [])]
        # Ключ 'field' появился в записях ПОСЛЕ первого прохода по названиям
        # должностей, поэтому у 558 записей его нет вовсе и признак «сигнал из
        # названия вакансии» давал ровный НОЛЬ — при 114 работодателях, которые
        # пришли именно оттуда. Восстанавливаем по самому запросу: текстовые
        # запросы второго прохода закавычены, запросы по должности — нет.
        по_названию = any(not (q or '').startswith('"')
                          for q in (r.get('queries') or []))
        только_холод = bool(назв) and all(_ХОЛОД.search(n) for n in назв)
        только_передвиж = bool(назв) and all(_ПЕРЕДВИЖ.search(n) for n in назв)
        hot = 3 if по_названию else 2
        if только_холод or только_передвиж:
            hot = 1
        кл = (классы.get(r['key']) or {})
        сч['класс:' + (кл.get('класс') or 'неразмечен')] += 1

        строка = {
            'key': r['key'], 'employer': r['employer'],
            'employer_url': r.get('employer_url') or '', 'sites': r.get('sites') or [],
            'n_vac': r.get('n') or 0, 'areas': r.get('areas') or {},
            'vacancies': r.get('vacancies') or [], 'queries': r.get('queries') or [],
            'fields': r.get('fields') or [],
            'inn': inn, 'доказательство': доказ, 'качество': качество,
            'замечание': замечание, 'site_inn': site_inn,
            'кандидаты': cand[:3],
            'егрюл_имя': (m or {}).get('name') or (
                next((c['name'] for c in cand if c['inn'] == inn), '') if inn else ''),
            'окved': next((c['okved'] for c in cand if c['inn'] == inn), '') if inn else '',
            'регион': next((c['region'] for c in cand if c['inn'] == inn), '') if inn else '',
            'город': next((c['city'] for c in cand if c['inn'] == inn), '') if inn else '',
            'в_базе_обзвона': bool(m), 'в_enrich': есть_e,
            'новая': bool(inn) and not (m or есть_e),
            'база': m or {}, 'hotness': hot,
            'только_холодильные': только_холод, 'только_передвижные': только_передвиж,
            'класс': кл.get('класс') or 'неразмечен',
            'профиль': кл.get('профиль') or '', 'класс_почему': кл.get('почему') or '',
        }
        строки.append(строка)
        fh.write(json.dumps(строка, ensure_ascii=False) + '\n')
    fh.flush()
    os.fsync(fh.fileno())
    fh.close()
    shutil.copyfile(MERGED, os.path.join(STORE, 'hh_inv_merged2_stream.jsonl'))

    print('--- СЧЁТЧИКИ ---', flush=True)
    for k in sorted(сч):
        print(f'  {k}: {сч[k]}')

    лиды = [s for s in строки if s['inn'] and s['класс'] in
            ('конечный потребитель', 'подрядчик', 'неясно', 'неразмечен')]
    новые_лиды = [s for s in лиды if s['новая']]
    print(f'--- ЛИДЫ (не конкурент, не кадровое агентство): {len(лиды)}, '
          f'из них НОВЫХ {len(новые_лиды)} ---', flush=True)

    if apply:
        ок = [s for s in строки if s['inn'] and s['качество'] in ('сильное', 'среднее')
              and s['класс'] != 'кадровое агентство']
        print(f'--- ЗАПИСЬ {len(ок)} компаний ---', flush=True)
        for s in ок:
            inn = s['inn']
            поля = {}
            if inn not in в_enrich:
                поля['name'] = s['егрюл_имя'] or s['employer']
                поля['region'] = s['регион'] or (s['база'] or {}).get('region') or ''
                поля['okved'] = s['окved'] or (s['база'] or {}).get('okved') or ''
                поля['cand_site'] = (s['sites'] or [''])[0]
                if (s['база'] or {}).get('division'):
                    поля['division'] = s['база']['division']
            if s['класс'] == 'конкурент':
                поля['is_competitor'] = 1
            if поля:
                db.upsert_company(inn, **{k: v for k, v in поля.items() if v})
                сч['записано_компаний'] += 1
            v0 = (s['vacancies'] or [{}])[0]
            имена = ', '.join(sorted({(v.get('name') or '')[:60]
                                      for v in s['vacancies']})[:4])
            что = (f'нанимает в компрессорное хозяйство: {имена}. '
                   f'вакансий за 30 дней {s["n_vac"]}, города: '
                   f'{", ".join(list(s["areas"])[:4])}. '
                   f'кто это: {s["класс"]}'
                   + (f' ({s["класс_почему"]})' if s['класс_почему'] else '')
                   + f'. привязка: {s["доказательство"]}'
                   + (f'. ВНИМАНИЕ: {s["замечание"]}' if s['замечание'] else '')
                   + (' [только холодильные компрессоры]' if s['только_холодильные'] else '')
                   + (' [только передвижные дизельные]' if s['только_передвижные'] else ''))
            db.add_signal(inn, source='hh-вакансия',
                          event_type='нанимает в компрессорную', what=что,
                          source_url=v0.get('url') or s['employer_url'],
                          hotness=s['hotness'], ts=v0.get('published') or '')
            сч['записано_сигналов'] += 1
            db.mark_stage(inn, 'hh_inversion',
                          f'{s["качество"]}: {s["доказательство"][:80]}')
        print(f'записано компаний {сч["записано_компаний"]}, '
              f'сигналов {сч["записано_сигналов"]}', flush=True)

    print('--- РАСХОЖДЕНИЯ ПРИВЯЗКИ (первые 10) ---', flush=True)
    for s in [x for x in строки if x['замечание']][:10]:
        print(f'  {s["employer"][:32]:32s} итог={s["inn"]} | {s["замечание"][:70]}')
    # ПОХОЖЕСТЬ НА ПРОФИЛЬ: ОКВЭД, выручка, регион — по тем, кого записываем
    from collections import Counter as _C
    print('--- ПРОФИЛЬ ЛИДОВ ---', flush=True)
    print('  профиль по разметке:', _C(s['профиль'] for s in лиды).most_common())
    print('  ОКВЭД (2 знака) у лидов, топ 12:',
          _C((s['окved'] or '?')[:2] for s in лиды).most_common(12))
    рев = [(s['база'] or {}).get('revenue_rub') for s in лиды
           if (s['база'] or {}).get('revenue_rub')]
    рев = sorted(x for x in рев if isinstance(x, (int, float)))
    if рев:
        print(f'  выручка известна у {len(рев)} лидов из {len(лиды)} '
              f'(только те, кто в базе обзвона): медиана '
              f'{рев[len(рев)//2]/1e6:.0f} млн ₽, свыше 1 млрд — '
              f'{sum(1 for x in рев if x >= 1e9)}')
    print('  регионов у лидов:', len({s["регион"] for s in лиды if s["регион"]}))
    print('  сигнал из названия вакансии / только из текста:',
          sum(1 for s in лиды if s['hotness'] == 3), '/',
          sum(1 for s in лиды if s['hotness'] == 2))
    print('  только передвижные дизельные:',
          sum(1 for s in лиды if s['только_передвижные']),
          '| только холодильные:', sum(1 for s in лиды if s['только_холодильные']))
    print('--- НОВЫЕ ЛИДЫ, топ 15 по числу вакансий ---', flush=True)
    for s in sorted(новые_лиды, key=lambda x: -x['n_vac'])[:15]:
        print(f'  {s["inn"]} {s["employer"][:30]:30s} вак={s["n_vac"]:3d} '
              f'{s["класс"][:12]:12s} {(s["окved"] or "")[:30]:30s} {s["регион"][:16]}')
    print('=== ФИНАЛЬНЫЕ СЧЁТЧИКИ ===', flush=True)
    for k in sorted(сч):
        print(f'  {k}: {сч[k]}')
    print(f'поток {MERGED}, {time.time()-t0:.0f}с', flush=True)


if __name__ == '__main__':
    main()
    os._exit(0)
