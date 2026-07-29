# -*- coding: utf-8 -*-
"""ЗАМЕР 2ГИС по нашей базе: охват карточек, телефоны, подписи отделов.

Верификация «это та самая компания, а не тёзка»: домен сайта из карточки ==
наш домен, ИЛИ телефон из карточки есть в sales_base, ИЛИ все токены имени
совпали. Без якоря карточку не засчитываем.
Ничего не пишем в базу — разведка.
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
# подписи, которые для нас ЦЕННЫ (техника/снабжение), а не общий номер
ТЕХ = re.compile(r'снабжен|закуп|сбыт|главн\w*\s*(инженер|энергет|механ|техн)|'
                 r'производств|техническ|сервис|ремонт|энерг|механ|склад|'
                 r'логист|тендер|коммерческ|приемн|приёмн|секретар|канцеляр', re.I)


def P(*a):
    print(*a)
    sys.stdout.flush()


def гет(u, тайм=25):
    h = {'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}
    try:
        r = EC._DIRECT.open(urllib.request.Request(u, headers=h), timeout=тайм)
        return r.read(), r.headers.get('Content-Type', ''), r.status
    except Exception as ex:  # noqa: BLE001
        тело = b''
        try:
            тело = ex.read()[:300]
        except Exception:  # noqa: BLE001
            pass
        return тело, f'ОШИБКА {type(ex).__name__}: {str(ex)[:70]}', 0


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


def десять(p):
    d = re.sub(r'\D', '', str(p or ''))
    return d[-10:] if len(d) >= 10 else ''


def контакты(it):
    """[(тип, значение, подпись)] из всех contact_groups карточки."""
    out = []
    for g in (it.get('contact_groups') or []):
        for c in (g.get('contacts') or []):
            out.append((c.get('type'), c.get('value') or '',
                        (c.get('comment') or '').strip(),
                        c.get('text') or '', c.get('url') or ''))
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
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
        if len(пул) >= n:
            break

    ст = {'компаний': len(пул), 'карточка': 0, 'тел_всего': 0, 'тел_подпись': 0,
          'тел_тех': 0, 'email': 0, 'сайт_якорь': 0, 'тел_якорь': 0, 'имя_якорь': 0,
          'нет_карточки': 0}
    примеры = []
    for c in пул:
        бренд = EC.бренд_компании(c['name'], c['site'])
        наш_дом = EC._domain('http://' + c['site'].replace('http://', '').replace('https://', ''))
        варианты = []
        if c['region']:
            варианты.append(f'{бренд} {c["region"]}')
        варианты.append(бренд)
        карта, чем = None, ''
        for q in варианты:
            items, err = апи('items', q=q, page_size=8)
            time.sleep(0.35)
            if not items:
                continue
            токены = [t for t in re.findall(r'[а-яёa-z]{4,}', бренд.lower())][:3]
            for it in items:
                кс = контакты(it)
                домены = {EC._domain(x) for (тип, v, ком, t, u) in кс
                          if тип == 'website' for x in [(u or t)]}
                тел10 = {десять(v) for (тип, v, ком, t, u) in кс if тип == 'phone'}
                имя_карт = (it.get('name') or '').lower()
                if наш_дом and наш_дом in домены:
                    карта, чем = it, 'сайт'
                    break
                if c['phones'] and (тел10 & set(c['phones'])):
                    карта, чем = it, 'телефон'
                    break
                if токены and all(t in имя_карт for t in токены):
                    карта, чем = it, 'имя'
                    break
            if карта:
                break
        if not карта:
            ст['нет_карточки'] += 1
            P(f'  [-] {c["inn"]} {бренд[:34]!r} ({c["region"][:18]}) — карточки нет')
            continue
        ст['карточка'] += 1
        ст['сайт_якорь' if чем == 'сайт' else
           ('тел_якорь' if чем == 'телефон' else 'имя_якорь')] += 1
        кс = контакты(карта)
        тел = [(v, ком) for (тип, v, ком, t, u) in кс if тип == 'phone']
        почты = [v for (тип, v, ком, t, u) in кс if тип == 'email']
        ст['тел_всего'] += len(тел)
        ст['email'] += len(почты)
        подп = [(v, ком) for v, ком in тел if ком]
        ст['тел_подпись'] += len(подп)
        ст['тел_тех'] += sum(1 for v, ком in подп if ТЕХ.search(ком))
        for v, ком in подп:
            if len(примеры) < 14:
                примеры.append((бренд[:30], v, ком))
        P(f'  [+] {c["inn"]} {бренд[:30]!r} якорь={чем} тел={len(тел)} '
          f'подпись={len(подп)} email={len(почты)} | {тел[:4]}')

    P('')
    for e in примеры:
        P('  ПРИМЕР:', e)
    P('ИТОГ 2ГИС: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
