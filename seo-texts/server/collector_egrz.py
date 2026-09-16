# -*- coding: utf-8 -*-
"""Коллектор ЕГРЗ — Единый государственный реестр заключений экспертизы
проектной документации (задача 1 из TZ-RANNEE-SOBYTIE.md).

Зачем. Заключение экспертизы выдаётся на стадии «проектирование» — до стройки и
до закупки оборудования. Это на три-четыре шага раньше новости про ленточку.
В карточке заключения ПРЯМЫМ ТЕКСТОМ стоят застройщик и технический заказчик
с ОГРН/ИНН/КПП — значит ИНН берётся из источника, dadata не нужна
(в отличие от новостных коллекторов, где имя приходится угадывать).

ГДЕ БЕРЁМ (проверено на сервере владельца 16.09.2026, подробности —
в COLLECTOR-EGRZ.md):

  * `egrz.gov.ru` в ТЗ — **опечатка, такого хоста не существует** (NXDOMAIN).
    Рабочий сайт ГИС ЕГРЗ — `https://egrz.ru` (Angular-SPA).
  * Данные SPA берёт из ОТКРЫТОГО OData-сервиса `https://open-api.egrz.ru/api/`,
    набор `PublicRegistrationBook` — публичная книга регистрации заключений.
    Без авторизации, без капчи, без ключа. На 16.09.2026 в нём 596 907 записей.

ЧЕГО В ИСТОЧНИКЕ НЕТ. Сметной стоимости в публичной книге НЕТ: у сущности
42 поля, поля стоимости среди них нет (сервер на `$select=EstimatedCost`
отвечает 400 «Could not find a property named…»). Поэтому `sum` коллектор
отдаёт ПУСТЫМ, а не выдумывает. Смета лежит в теле заключения, а оно доступно
только в личном кабинете ЕГРЗ по доверенности. Обходные пути — в COLLECTOR-EGRZ.md.

Формат item — как у остальных коллекторов news_scan.py:
{title, link, pubDate, source, tier, collector, query}
плюс поля, которые даёт именно этот источник:
{company_name, company_name_short, inn, inn_conf, company_role, sum, region,
 region_code, stage, event_date, what, expertise_number, work_type,
 functional_purpose, address, expertise_org, expertise_org_inn}

Импорт без побочных эффектов. Ручной прогон: `python collector_egrz.py`.
"""
import datetime as _dt
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://open-api.egrz.ru/api/'
SITE = 'https://egrz.ru'
ENTITY = 'PublicRegistrationBook'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

# Сервер режет страницу: $top>150 -> HTTP 400. $skip работает (проверено на 100000).
PAGE = 150

# --------------------------------------------------------------- сеть
# Как в news_scan: системный SOCKS-прокси сервера режет часть хостов, а гос-сайты
# отдают цепочку Russian Trusted CA -> обычный urlopen падает на верификации.
# Идём мимо системного прокси с неверифицирующим контекстом.
_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=_SSLCTX))


def _get_json(url, timeout=60, tries=3):
    """GET -> (код, распарсенный JSON или {}). Транзиентные ошибки ретраим."""
    head = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru,en;q=0.8',
            # SPA ходит с этими заголовками; без них сервис тоже отвечает,
            # но пусть запрос выглядит как обычный запрос портала.
            'Origin': SITE, 'Referer': SITE + '/'}
    last = 0
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=head)
            body = _NOPROXY.open(req, timeout=timeout).read()
            return 200, json.loads(body.decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            # 400 — наша ошибка в запросе, ретраить бессмысленно
            last = e.code
            if e.code == 400:
                try:
                    return 400, json.loads((e.read() or b'{}').decode('utf-8', 'replace'))
                except Exception:  # noqa: BLE001
                    return 400, {}
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
        except Exception:  # noqa: BLE001
            last = -1
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    return last, {}


# --------------------------------------------------------------- отбор объектов
# КОСФН — классификатор объектов по функциональному назначению, поле
# FunctionalPurpose вида «06.03.005.003 Здание цеха по производству масложировой
# продукции». Разделы (замер по реестру за 90 дней, 16.09.2026):
#   01 среда населённых пунктов 6802 | 02 образование/культура 2800 |
#   03 здравоохранение/спорт 1122 | 04 транспорт 1744 | 05 энергетика 255 |
#   06 сельское хозяйство и пищепром 294 | 07 химическая промышленность 85 |
#   08 добывающая промышленность 304 | 09 металлургия 39 | 10 металлургия(ред.2) 66 |
#   11 машиностроение/обработка 173 | 12 инженерные сети 2266 | 19 жильё 60 |
#   20 дороги 82.
# Берём отраслевые разделы 06–11 плюс два промышленных «вкрапления» раздела 01:
#   01.01.006 — объекты промышленных площадок (промпарки, логистические центры),
#   01.06.001 — производственно-технические здания, склады, АБК.
# Разделы 05 (энергосети/подстанции) и 12 (котельные, водопровод, ЛЭП) по
# умолчанию НЕ берём: там коммунальная инфраструктура, а не производство.
# Эти префиксы проверены запросами startswith(FunctionalPurpose,'…').
SECTIONS_PROM = ('06.', '07.', '08.', '09.', '10.', '11.', '01.01.006', '01.06.001')

# Дополнительные разделы, которые владелец может включить точечно:
#   '05.' — энергетика (ТЭС, котельные крупные), '12.01.001.002' — здание котельной.
SECTIONS_ENERGO = ('05.', '12.01.001.002')

# Вид работ. Капремонт (9098 записей из 17682 за 90 дней) — это ремонт готового,
# новое оборудование там берут редко. Нас интересуют стройка и реконструкция.
WORK_TYPES_CAPEX = ('Строительство', 'Реконструкция')

# Отсев внутри отраслевых разделов: соц/жильё/дороги туда изредка попадают
# (например аптека с кодом фарм-производства или ведомственное общежитие).
_STOP_RE = re.compile(
    r'жил(?:ой|ая|ые|ищ)|многоквартир|общежит|апартамент|детск(?:ий|ого) сад|'
    r'школ[аыу]|гимнази|лице[йя]|больниц|поликлиник|амбулатор|фельдшер|ФАП\b|'
    r'аптек|храм|церков|мечет|часовн|кладбищ|крематор|стадион|бассейн|'
    r'спортивн|благоустройств|тротуар|сквер|детск(?:ая|ой) площадк|'
    r'автомобильн(?:ая|ой) дорог|улиц[аы]|путепровод|мост(?:а|ы)?\b|'
    r'наружн(?:ое|ого) освещени|пешеходн', re.I)

# Признаки настоящего производства — используются, только если задан require_prod_kw
_PROD_RE = re.compile(
    r'завод|цех|производств|фабрик|комбинат|линия|технологическ|промышленн|'
    r'перерабат|элеватор|склад|логистич|компрессорн|котельн|установк|'
    r'нефт|газоперер|металл|литейн|птичник|свинарник|коровник|теплиц|'
    r'убойн|молочн|мясоперераб|зернос|обогатительн|рудник|карьер|шахт', re.I)

_INN_RE = re.compile(r'ИНН:\s*(\d{10,12})')
# Длинные ОПФ из ЕГРЮЛ -> привычные аббревиатуры (для короткого имени в заголовке)
_OPF = (
    ('ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ', 'ООО'),
    ('ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ПАО'),
    ('НЕПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'НАО'),
    ('ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ЗАО'),
    ('ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ОАО'),
    ('АКЦИОНЕРНОЕ ОБЩЕСТВО', 'АО'),
    ('КРЕСТЬЯНСКОЕ (ФЕРМЕРСКОЕ) ХОЗЯЙСТВО', 'КФХ'),
    ('ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ', 'ИП'),
    ('ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ', 'ФГУП'),
    ('ГОСУДАРСТВЕННОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ', 'ГУП'),
    ('МУНИЦИПАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ', 'МУП'),
)


def _esc(s):
    """Экранирование строкового литерала OData (одинарная кавычка удваивается)."""
    return str(s or '').replace("'", "''")


def _short_name(full):
    """«ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СИБИРСКАЯ СЕМЕЧКА"» ->
    «ООО "СИБИРСКАЯ СЕМЕЧКА"». Само наименование НЕ трогаем: перевод регистра
    ломает имена собственные, а дальше по цепочке имя идёт в матчинг."""
    s = re.sub(r'\s+', ' ', str(full or '')).strip()
    up = s.upper()
    for long_form, short in _OPF:
        if up.startswith(long_form):
            return (short + ' ' + s[len(long_form):].strip()).strip()
    return s


def _org(blob):
    """Разобрать строку организации ЕГРЗ.

    Формат: «НАИМЕНОВАНИЕ (ОГРН: …, ИНН: …, КПП: …, ОКТМО: …,
    Муниципальное образование: …, МЕСТО НАХОЖДЕНИЯ и АДРЕС: …)».
    Возвращает (наименование, ИНН) или ('', '')."""
    s = re.sub(r'\s+', ' ', str(blob or '')).strip()
    if not s:
        return '', ''
    m = _INN_RE.search(s)
    inn = m.group(1) if m else ''
    name = re.split(r'\s*\((?:ОГРН|ИНН)[:\s]', s, 1)[0].strip(' ,;')
    return name, inn


def _company(rec):
    """Кого считаем компанией события. Порядок: застройщик (он покупает
    оборудование) -> застройщик-он-же-техзаказчик -> технический заказчик."""
    for field, role in (('DeveloperOrganizationInfo', 'застройщик'),
                        ('DeveloperAndTechnicalCustomerOrganizationInfo',
                         'застройщик и технический заказчик'),
                        ('TechnicalCustomerOrganizationInfo', 'технический заказчик')):
        name, inn = _org(rec.get(field))
        if name:
            return name, inn, role
    return '', '', ''


def _region(rec):
    """«Волгоградская область - 34» -> («Волгоградская область», «34»)."""
    s = str(rec.get('SubjectRf') or '').strip()
    code = str(rec.get('SubjectRfCode') or '').strip()
    name = re.sub(r'\s*-\s*\d+\s*$', '', s)
    return name, code


def _build_filter(date_from, sections, work_types, positive_only, region_codes, keywords):
    """Собрать OData $filter. Все условия проверены на боевом сервисе."""
    parts = ['ExpertiseConclusionDate gt %s' % date_from]
    if positive_only:
        # 16 890 положительных против 792 отрицательных за 90 дней:
        # отрицательное заключение — проект завернули, событие не наше.
        parts.append("ExpertiseResultType eq 'Положительное заключение'")
    if work_types:
        parts.append('(' + ' or '.join("WorkType eq '%s'" % _esc(w) for w in work_types) + ')')
    if sections:
        parts.append('(' + ' or '.join("startswith(FunctionalPurpose,'%s')" % _esc(s)
                                       for s in sections) + ')')
    if region_codes:
        parts.append('(' + ' or '.join("SubjectRfCode eq '%s'" % _esc(r)
                                       for r in region_codes) + ')')
    if keywords:
        parts.append('(' + ' or '.join(
            "contains(tolower(ExpertiseObjectName),tolower('%s'))" % _esc(k.lower())
            for k in keywords) + ')')
    return ' and '.join(parts)


def _split_regions(regions):
    """regions принимает и коды субъектов («34», 34), и названия («Алтайский край»).
    Коды уходят в серверный фильтр, названия — в клиентский (подстрокой)."""
    codes, names = [], []
    for r in (regions or []):
        s = str(r).strip()
        if not s:
            continue
        if s.isdigit():
            codes.append(s.zfill(2) if len(s) == 1 else s)
        else:
            names.append(s.lower())
    return codes, names


def _page(flt, skip, top=PAGE, order='ExpertiseConclusionDate desc'):
    q = {'$filter': flt, '$top': str(top), '$skip': str(skip), '$orderby': order,
         '$count': 'true'}
    url = API + ENTITY + '?' + urllib.parse.urlencode(q)
    return _get_json(url)


def col_egrz(days=90, max_items=400, regions=None, sections=SECTIONS_PROM,
             work_types=WORK_TYPES_CAPEX, positive_only=True, keywords=None,
             require_prod_kw=False, drop_social=True, verbose=False):
    """Заключения экспертизы по производственным/промышленным объектам.

    days            — глубина по дате заключения (ExpertiseConclusionDate);
    max_items       — потолок числа item'ов (страницами по 150);
    regions         — коды субъектов РФ и/или названия, None = вся страна;
    sections        — префиксы кодов КОСФН (см. SECTIONS_PROM / SECTIONS_ENERGO);
    work_types      — вид работ, по умолчанию стройка+реконструкция без капремонта;
    positive_only   — только положительные заключения;
    keywords        — доп. условие «слово встречается в названии объекта» (OR);
    require_prod_kw — жёсткий клиентский гейт по производственной лексике;
    drop_social     — выкидывать жильё/соц/дороги, если просочились в отраслевой код.

    Возвращает список item'ов. Сеть недоступна/сервис ответил 400 — вернётся [],
    исключения наружу не летят (как у остальных коллекторов).
    """
    date_from = (_dt.datetime.utcnow() - _dt.timedelta(days=int(days))
                 ).strftime('%Y-%m-%dT00:00:00Z')
    codes, region_names = _split_regions(regions)
    flt = _build_filter(date_from, sections, work_types, positive_only, codes, keywords)

    code, data = _page(flt, 0)
    if code != 200:
        # Фолбэк: если сервис не принял составной фильтр (сменилась схема полей),
        # тянем только по дате и фильтруем на своей стороне — лучше медленно, чем никак.
        if verbose:
            sys.stderr.write('ЕГРЗ: фильтр отвергнут (code=%s), фолбэк на дату\n' % code)
        flt = 'ExpertiseConclusionDate gt %s' % date_from
        code, data = _page(flt, 0)
        if code != 200:
            return []

    total = data.get('@odata.count')
    items, seen, skip = [], set(), 0
    while True:
        for rec in (data.get('value') or []):
            key = rec.get('Key')
            if not key or key in seen:
                continue
            seen.add(key)
            it = _to_item(rec, sections, region_names, require_prod_kw, drop_social)
            if it:
                items.append(it)
                if len(items) >= int(max_items):
                    if verbose:
                        sys.stderr.write('ЕГРЗ: всего по фильтру %s, взято %d\n'
                                         % (total, len(items)))
                    return items
        skip += PAGE
        if total is not None and skip >= int(total):
            break
        if skip > 20000:      # предохранитель от бесконечной прокрутки
            break
        code, data = _page(flt, skip)
        if code != 200 or not (data.get('value') or []):
            break
    if verbose:
        sys.stderr.write('ЕГРЗ: всего по фильтру %s, взято %d\n' % (total, len(items)))
    return items


def _to_item(rec, sections, region_names, require_prod_kw, drop_social):
    """Запись книги регистрации -> item коллектора (или None, если отсеяли)."""
    obj = re.sub(r'\s+', ' ', str(rec.get('ExpertiseObjectName') or '')).strip().strip('"')
    if not obj:
        return None
    fp = str(rec.get('FunctionalPurpose') or '')
    # клиентская подстраховка: в фолбэк-режиме серверного фильтра по разделам не было
    if sections and fp and not any(fp.startswith(s) for s in sections):
        return None
    if drop_social and _STOP_RE.search(obj):
        return None
    if require_prod_kw and not _PROD_RE.search(obj + ' ' + fp):
        return None

    region, region_code = _region(rec)
    if region_names and not any(n in region.lower() for n in region_names):
        return None

    company, inn, role = _company(rec)
    work = str(rec.get('WorkType') or '').strip()
    num = str(rec.get('ExpertiseNumber') or '').strip()
    date = str(rec.get('ExpertiseConclusionDate') or '')
    short = _short_name(company)
    addr = re.sub(r'\s+', ' ', str(rec.get('ExpertiseObjectAddress') or '')).strip()
    purpose = fp.split(' ', 1)[1] if ' ' in fp else fp

    # Заголовок пишем так, чтобы он читался и человеком в лид-деске, и
    # классификатором extract_event: кто, что, где, на какой стадии.
    head = short or 'Застройщик не указан'
    title = ('%s — положительное заключение экспертизы проекта: %s (%s, %s)'
             % (head, obj, region or 'регион не указан', (work or 'строительство').lower()))
    what = ('%s. %s. Заключение %s от %s. Назначение: %s'
            % (obj, work or 'Строительство', num, date[:10], purpose or 'не указано'))
    exp_name, exp_inn = _org(rec.get('ExpertiseOrganizatioInfo'))

    return {
        # --- обязательный контракт коллектора news_scan ---
        'title': title[:400],
        'link': '%s/organisation/reestr/detail/%s' % (SITE, rec.get('Key')),
        'pubDate': date,                 # ISO-8601, напр. 2026-09-15T13:09:37Z
        'source': 'ЕГРЗ',
        'tier': 2,                       # как ФРП: реестр, а не пересказ новости
        'collector': 'egrz',
        'query': fp[:40] or 'КОСФН',     # по какому разделу нашли
        # --- то, что даёт именно этот источник ---
        'company_name': company,         # как в ЕГРЮЛ, именительный падеж
        'company_name_short': short,     # 'ООО "…"' для заголовков
        'company_role': role,
        'inn': inn,
        'inn_conf': 'high' if inn else '',   # ИНН из реестра, dadata не нужна
        'sum': '',                       # сметной стоимости в публичном ЕГРЗ НЕТ
        'region': region,
        'region_code': region_code,
        'stage': 'проект',
        'event_date': date[:10],         # ISO YYYY-MM-DD (задача 6 ТЗ)
        'what': what,
        'expertise_number': num,
        'work_type': work,
        'functional_purpose': fp,
        'address': addr,
        'expertise_org': exp_name,
        'expertise_org_inn': exp_inn,
    }


if __name__ == '__main__':
    t0 = time.time()
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    res = col_egrz(days=days, max_items=cap, verbose=True)

    with_inn = sum(1 for i in res if i['inn'])
    by_reg = {}
    for i in res:
        by_reg[i['region']] = by_reg.get(i['region'], 0) + 1

    for i in res[:10]:
        print('-' * 100)
        print('title :', i['title'][:200])
        print('link  :', i['link'])
        print('pub   :', i['pubDate'], '| event_date:', i['event_date'],
              '| source:', i['source'], '| tier:', i['tier'], '| collector:', i['collector'])
        print('компан:', i['company_name'][:90], '| ИНН:', i['inn'] or '-',
              '(%s, %s)' % (i['company_role'], i['inn_conf'] or 'нет'))
        print('регион:', i['region'], '| стадия:', i['stage'], '| смета:',
              i['sum'] or '(нет в источнике)')
        print('что   :', i['what'][:200])
        print('КОСФН :', i['functional_purpose'][:90])
    print('=' * 100)
    print('ЕГРЗ: за %d дней получено %d заключений, с ИНН %d (%.0f%%), за %.1f с'
          % (days, len(res), with_inn,
             100.0 * with_inn / max(1, len(res)), time.time() - t0))
    print('топ регионов:', sorted(by_reg.items(), key=lambda x: -x[1])[:8])
