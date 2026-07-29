# -*- coding: utf-8 -*-
"""ЗАМЕР 2ГИС, версия 2 — с ЧЕСТНЫМ запросом.

Первый замер дал 6/20, но промахи были МОИ, а не источника:
  * EC.бренд_компании заточен под hh и отдаёт ДОМЕН ('aecc', 'cryogenmash',
    'lorp') — как запрос в справочник это мусор;
  * у половины строк enrich.db region пуст, а 2ГИС без города отвечает 404.
Чиним: имя берём уставное без ОПФ, город достаём из dadata по ИНН, пробуем
несколько формулировок запроса. Ничего не пишем в базу.
"""
import json
import re
import sqlite3
import sys
import time
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'
КЛЮЧ = 'ruxlih0718'
ПОЛЯ = ('items.contact_groups,items.address,items.org,items.rubrics,'
        'items.external_content,items.region_id')
ТЕХ = re.compile(r'снабжен|закуп|сбыт|главн|производств|техническ|сервис|ремонт|'
                 r'энерг|механ|склад|логист|тендер|коммерческ|диспетчер|аварийн', re.I)
ПРИЁМ = re.compile(r'приемн|приёмн|секретар|канцеляр|справочн|горячая|контакт-центр', re.I)


def P(*a):
    print(*a)
    sys.stdout.flush()


def гет(u, тайм=25):
    h = {'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}
    try:
        r = EC._DIRECT.open(urllib.request.Request(u, headers=h), timeout=тайм)
        return r.read(), r.headers.get('Content-Type', ''), r.status
    except Exception as ex:  # noqa: BLE001
        return b'', f'ОШИБКА {type(ex).__name__}', 0


def апи(путь, **prm):
    prm.setdefault('key', КЛЮЧ)
    prm.setdefault('fields', ПОЛЯ)
    u = f'https://catalog.api.2gis.ru/3.0/{путь}?' + urllib.parse.urlencode(prm)
    raw, ct, st = гет(u)
    if not raw:
        return None, str(ct)
    txt = EC._раскодировать(raw, ct)
    try:
        d = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None, 'не-JSON'
    код = (d.get('meta') or {}).get('code')
    if код != 200:
        return None, f'code={код}'
    return (d.get('result') or {}).get('items') or [], ''


_ДД = {}


def дадата(inn):
    """(город, короткое_имя, адрес) из dadata по ИНН. Кэш в памяти процесса."""
    if inn in _ДД:
        return _ДД[inn]
    tok = EC._read_secret('DADATA_TOKEN')
    из = ('', '', '')
    if tok and inn:
        try:
            body = json.dumps({'query': str(inn)}).encode()
            req = urllib.request.Request(
                'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                data=body, method='POST',
                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                         'Authorization': f'Token {tok}'})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())
            s = (d.get('suggestions') or [{}])[0]
            dd = s.get('data') or {}
            ад = (dd.get('address') or {}).get('data') or {}
            город = (ад.get('city') or ад.get('settlement')
                     or ад.get('region') or '')
            имя = ((dd.get('name') or {}).get('short_with_opf')
                   or (dd.get('name') or {}).get('short') or s.get('value') or '')
            из = (город, имя, (dd.get('address') or {}).get('value') or '')
        except Exception:  # noqa: BLE001
            из = ('', '', '')
    _ДД[inn] = из
    return из


_ОПФ = re.compile(
    r'\b(АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|'
    r'ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ|ФЕДЕРАЛЬНОЕ\s+ГОСУДАРСТВЕННОЕ|'
    r'ГОСУДАРСТВЕННОЕ\s+БЮДЖЕТНОЕ\s+УЧРЕЖДЕНИЕ|УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ|'
    r'ПРЕДСТАВИТЕЛЬСТВО|ФИЛИАЛ|ООО|ОАО|ЗАО|ПАО|АО|ФГУП|ГУП|МУП|ФКП|ГБУ|АНО)\b',
    re.I)


def имена(name, dd_имя):
    """Кандидаты-названия для поиска в справочнике, от точного к грубому."""
    out = []
    for сыр in (dd_имя, name):
        сыр = str(сыр or '').strip()
        if not сыр:
            continue
        m = re.search(r'[«"]([^«»"]{3,60})[»"]', сыр) or re.search(r'[«"]([^«»"]{3,60})$', сыр)
        if m:
            out.append(m.group(1).strip())
        чист = _ОПФ.sub(' ', сыр)
        чист = re.sub(r'\s+', ' ', чист).strip().strip('"«»').strip()
        if чист:
            out.append(чист)
    видел, res = set(), []
    for x in out:
        k = x.lower()
        if k not in видел and len(x) >= 3:
            видел.add(k)
            res.append(x)
    return res[:3]


def десять(p):
    d = re.sub(r'\D', '', str(p or ''))
    return d[-10:] if len(d) >= 10 else ''


def контакты(it):
    out = []
    for g in (it.get('contact_groups') or []):
        for c in (g.get('contacts') or []):
            out.append((c.get('type'), c.get('value') or '',
                        (c.get('comment') or '').strip(),
                        c.get('text') or '', c.get('url') or ''))
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    старт = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    d = json.load(open(БАЗА, encoding='utf-8'))
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    else:
        строки = d
    по_инн = {}
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in по_инн:
            по_инн[i] = x
    con = sqlite3.connect(EDB.DB_PATH)
    cur = con.cursor()
    пул = []
    for inn, x in по_инн.items():
        r = cur.execute('SELECT name, site, region FROM companies WHERE inn=?',
                        (inn,)).fetchone()
        if not r or not (r[1] or ''):
            continue
        пул.append({'inn': inn, 'name': r[0] or str(x.get('name') or ''),
                    'site': r[1], 'region': r[2] or '',
                    'phones': [десять(p) for p in (x.get('phones') or [])]})
    пул = пул[старт:старт + n]

    ст = {'компаний': len(пул), 'карточка': 0, 'тел_всего': 0, 'тел_подпись': 0,
          'подпись_тех': 0, 'подпись_приём': 0, 'email': 0, 'нет_карточки': 0,
          'якорь_сайт': 0, 'якорь_телефон': 0, 'якорь_имя': 0, 'нет_города': 0}
    примеры = []
    for c in пул:
        город, ддимя, адрес = дадата(c['inn'])
        город = re.sub(r'^(г|город|пгт|с|село|рп)\.?\s+', '', город or '', flags=re.I)
        город = город or c['region']
        if not город:
            ст['нет_города'] += 1
        кандидаты = имена(c['name'], ддимя)
        наш_дом = EC._domain('http://' + re.sub(r'^https?://', '', c['site']))
        токены_вар = [[t for t in re.findall(r'[а-яёa-z]{4,}', k.lower())][:3]
                      for k in кандидаты]
        карта, чем, запрос = None, '', ''
        варианты = []
        for k in кандидаты:
            if город:
                варианты.append(f'{k} {город}')
        варианты += кандидаты
        for q in варианты:
            items, err = апи('items', q=q, page_size=10)
            time.sleep(0.3)
            if not items:
                continue
            for it in items:
                кс = контакты(it)
                домены = {EC._domain(x) for (тип, v, ком, t, u) in кс
                          if тип == 'website' for x in [(u or t)]}
                тел10 = {десять(v) for (тип, v, ком, t, u) in кс if тип == 'phone'}
                имя_карт = (it.get('name') or '').lower()
                if наш_дом and наш_дом in домены:
                    карта, чем, запрос = it, 'сайт', q
                elif c['phones'] and (тел10 & set(c['phones'])):
                    карта, чем, запрос = it, 'телефон', q
                elif any(тк and all(t in имя_карт for t in тк) for тк in токены_вар):
                    карта, чем, запрос = it, 'имя', q
                if карта:
                    break
            if карта:
                break
        if not карта:
            ст['нет_карточки'] += 1
            P(f'  [-] {c["inn"]} {кандидаты[:1]} город={город[:16]!r} — не сматчено')
            continue
        ст['карточка'] += 1
        ст['якорь_' + ('сайт' if чем == 'сайт' else
                       ('телефон' if чем == 'телефон' else 'имя'))] += 1
        кс = контакты(карта)
        тел = [(v, ком) for (тип, v, ком, t, u) in кс if тип == 'phone']
        почты = [v for (тип, v, ком, t, u) in кс if тип == 'email']
        подп = [(v, ком) for v, ком in тел if ком]
        ст['тел_всего'] += len(тел)
        ст['email'] += len(почты)
        ст['тел_подпись'] += len(подп)
        ст['подпись_тех'] += sum(1 for v, k in подп if ТЕХ.search(k))
        ст['подпись_приём'] += sum(1 for v, k in подп if ПРИЁМ.search(k))
        for v, k in подп:
            if len(примеры) < 20:
                примеры.append((кандидаты[0][:26], v, k))
        P(f'  [+] {c["inn"]} {кандидаты[0][:26]!r} якорь={чем} тел={len(тел)} '
          f'подпись={len(подп)} email={len(почты)} | {[(v, k) for v, k in тел][:4]}')

    P('')
    for e in примеры:
        P('  ПРИМЕР:', e)
    P('ИТОГ 2ГИС2: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
