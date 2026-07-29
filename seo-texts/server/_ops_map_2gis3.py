# -*- coding: utf-8 -*-
"""ЗАМЕР 2ГИС, версия 3 — считаем ВСЕ карточки компании, а не первую.

Замер-2 брал первую сматченную карточку и мог потерять главное: у завода
отделы бывают ОТДЕЛЬНЫМИ карточками («…, отдел сбыта»). Здесь собираем все
верифицированные карточки по всем вариантам запроса, плюс филиалы через
org_id+region_id, и печатаем их имена — чтобы увидеть отделы глазами.
Ничего не пишем в базу.
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
                 r'энерг|механ|склад|логист|тендер|коммерческ|диспетчер|аварийн|'
                 r'кадр|бухгалт|отдел', re.I)


def P(*a):
    print(*a)
    sys.stdout.flush()


def апи(путь, **prm):
    prm.setdefault('key', КЛЮЧ)
    prm.setdefault('fields', ПОЛЯ)
    u = f'https://catalog.api.2gis.ru/3.0/{путь}?' + urllib.parse.urlencode(prm)
    try:
        r = EC._DIRECT.open(urllib.request.Request(
            u, headers={'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}), timeout=25)
        raw = r.read()
    except Exception as ex:  # noqa: BLE001
        return None, f'ОШ {type(ex).__name__}'
    txt = EC._раскодировать(raw, 'charset=utf-8')
    try:
        d = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None, 'не-JSON'
    код = (d.get('meta') or {}).get('code')
    if код != 200:
        return None, f'code={код}'
    return (d.get('result') or {}).get('items') or [], ''


_ОПФ = re.compile(
    r'\b(АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|'
    r'ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ|ФЕДЕРАЛЬНОЕ\s+ГОСУДАРСТВЕННОЕ|'
    r'ГОСУДАРСТВЕННОЕ\s+БЮДЖЕТНОЕ\s+УЧРЕЖДЕНИЕ|УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ|'
    r'ПРЕДСТАВИТЕЛЬСТВО|ФИЛИАЛ|ООО|ОАО|ЗАО|ПАО|АО|ФГУП|ГУП|МУП|ФКП|ГБУ|АНО)\b', re.I)
_ДД = {}


def дадата(inn):
    if inn in _ДД:
        return _ДД[inn]
    tok = EC._read_secret('DADATA_TOKEN')
    из = ('', '')
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
            из = ((ад.get('city') or ад.get('settlement') or ад.get('region') or ''),
                  ((dd.get('name') or {}).get('short_with_opf') or s.get('value') or ''))
        except Exception:  # noqa: BLE001
            из = ('', '')
    _ДД[inn] = из
    return из


def имена(name, ддимя):
    out = []
    for сыр in (ддимя, name):
        сыр = str(сыр or '').strip()
        if not сыр:
            continue
        m = re.search(r'[«"]([^«»"]{3,60})[»"]', сыр) or re.search(r'[«"]([^«»"]{3,60})$', сыр)
        if m:
            out.append(m.group(1).strip())
        ч = re.sub(r'\s+', ' ', _ОПФ.sub(' ', сыр)).strip().strip('"«»')
        if ч:
            out.append(ч)
    вид, res = set(), []
    for x in out:
        if x.lower() not in вид and len(x) >= 3:
            вид.add(x.lower())
            res.append(x)
    return res[:2]


def десять(p):
    d = re.sub(r'\D', '', str(p or ''))
    return d[-10:] if len(d) >= 10 else ''


def контакты(it):
    out = []
    for g in (it.get('contact_groups') or []):
        for c in (g.get('contacts') or []):
            out.append((c.get('type'), c.get('value') or '',
                        (c.get('comment') or '').strip(), c.get('text') or '',
                        c.get('url') or ''))
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
        пул.append({'inn': inn, 'name': r[0] or str(x.get('name') or ''), 'site': r[1],
                    'region': r[2] or '', 'phones': [десять(p) for p in (x.get('phones') or [])]})
    пул = пул[старт:старт + n]

    ст = {'компаний': len(пул), 'с_карточками': 0, 'карточек_всего': 0,
          'тел_всего': 0, 'тел_уник': 0, 'тел_подпись': 0, 'подпись_отдел': 0,
          'email': 0, 'карточек_отдел_в_имени': 0}
    подписи, имена_карточек = [], []
    for c in пул:
        город, ддимя = дадата(c['inn'])
        город = re.sub(r'^(г|город|пгт|с|село|рп)\.?\s+', '', город or '', flags=re.I) or c['region']
        канд = имена(c['name'], ддимя)
        наш = EC._domain('http://' + re.sub(r'^https?://', '', c['site']))
        токены = [[t for t in re.findall(r'[а-яёa-z]{4,}', k.lower())][:3] for k in канд]
        найдено = {}
        варианты = [f'{k} {город}' for k in канд if город] + канд
        for q in варианты:
            items, err = апи('items', q=q, page_size=12)
            time.sleep(0.3)
            for it in (items or []):
                кс = контакты(it)
                домены = {EC._domain(x) for (тип, v, ком, t, u) in кс
                          if тип == 'website' for x in [(u or t)]}
                тел10 = {десять(v) for (тип, v, ком, t, u) in кс if тип == 'phone'}
                имк = (it.get('name') or '').lower()
                ок = ((наш and наш in домены) or (c['phones'] and (тел10 & set(c['phones'])))
                      or any(тк and all(t in имк for t in тк) for тк in токены))
                if ок:
                    найдено[it.get('id')] = it
        if not найдено:
            P(f'  [-] {c["inn"]} {канд[:1]} — нет')
            continue
        ст['с_карточками'] += 1
        ст['карточек_всего'] += len(найдено)
        увид = set()
        for it in найдено.values():
            имя_к = str(it.get('name') or '')
            имена_карточек.append(имя_к[:60])
            if re.search(r'отдел|служба|цех|управлен|склад|снабж|сбыт', имя_к, re.I):
                ст['карточек_отдел_в_имени'] += 1
            for (тип, v, ком, t, u) in контакты(it):
                if тип == 'email':
                    ст['email'] += 1
                if тип != 'phone':
                    continue
                ст['тел_всего'] += 1
                увид.add(десять(v))
                if ком:
                    ст['тел_подпись'] += 1
                    подписи.append((канд[0][:24], v, ком))
                    if ТЕХ.search(ком):
                        ст['подпись_отдел'] += 1
        ст['тел_уник'] += len({x for x in увид if x})
        P(f'  [+] {c["inn"]} {канд[0][:24]!r} карточек={len(найдено)} '
          f'тел={sum(1 for it in найдено.values() for x in контакты(it) if x[0] == "phone")} '
          f'| имена: {[str(i.get("name"))[:38] for i in list(найдено.values())[:3]]}')

    P('')
    for x in подписи[:20]:
        P('  ПОДПИСЬ:', x)
    P('ИТОГ 2ГИС3: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
