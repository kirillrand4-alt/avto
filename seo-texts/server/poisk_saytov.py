# -*- coding: utf-8 -*-
r"""Поиск сайтов у компаний без сайта — с обязательной проверкой находки.

Владелец 16.08: «запускай поиск сайта у тех, у кого его нету, из топ-30% по
выручке (включая базу обзвона)».

Почему проверка обязательна. Пилот на 300 компаниях: xmlriver вернул адрес у 287
(96%), но по содержимому страницы подтвердились только 60% — в базу иначе уезжают
catalog.expocentr.ru, datanewton.ru, check.tochka.com и сайты головных компаний
вместо дочек. Поэтому найденное сперва открывается, и только при совпадении ИНН
или названия попадает в companies.site; всё остальное ложится в cand_site.

Выручка в базе обзвона — ТЕКСТ вида «114,1 млрд руб.», поэтому сортировка идёт по
разобранному числу, а не по строке (иначе «9 млн» оказывается больше «114 млрд»).

    python poisk_saytov.py [сколько] [потоков]
"""
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
LOG = r'C:\sender\poisk_saytov.jsonl'
_ЕДИНИЦЫ = (('млрд', 1e9), ('млн', 1e6), ('тыс', 1e3))


def выручка(s):
    """«114,1 млрд руб.» -> 114100000000.0"""
    t = str(s or '').replace('\xa0', ' ').strip().lower()
    m = re.search(r'([\d][\d\s]*(?:[.,]\d+)?)', t)
    if not m:
        return 0.0
    try:
        ч = float(m.group(1).replace(' ', '').replace(',', '.'))
    except ValueError:
        return 0.0
    for сл, мн in _ЕДИНИЦЫ:
        if сл in t:
            return ч * мн
    return ч


def _slova(imya):
    t = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|АКЦИОНЕРНОЕ ОБЩЕСТВО|'
               r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ)\s*', '',
               (imya or '').upper()).strip(' "«»')
    return [w for w in re.split(r'[\s"«»,\-]+', t) if len(w) > 3]


def цели(skolko, dolya=0.30):
    """Топ-N% базы обзвона по выручке, у кого сайта нет нигде и кого ещё не искали."""
    o = sqlite3.connect(OBZVON)
    строки = []
    for inn, sites, rev, ns, nf, reg in o.execute(
            "select inn, coalesce(sites,''), coalesce(revenue,''), coalesce(name_short,''), "
            "coalesce(name_full,''), coalesce(region,'') from obzvon"):
        i = str(inn or '').strip()
        if not i:
            continue
        строки.append((выручка(rev), i, (sites or '').strip(), ns or nf, reg))
    o.close()
    строки.sort(reverse=True)
    порог_шт = int(len(строки) * dolya)
    верх = строки[:порог_шт]

    c = sqlite3.connect(BD)
    est = {str(r[0]) for r in c.execute(
        "select inn from companies where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''")}
    c.close()
    уже = set()
    if os.path.exists(LOG):
        with open(LOG, encoding='utf-8') as f:
            for s in f:
                try:
                    уже.add(json.loads(s).get('inn'))
                except Exception:  # noqa: BLE001
                    pass
    из = []
    for rev, i, sites, name, reg in верх:
        if sites or i in est or i in уже:
            continue
        из.append({'inn': i, 'name': name, 'city': reg, 'revenue': rev})
        if len(из) >= skolko:
            break
    return из, (верх[-1][0] if верх else 0), len(верх)


def прогон(skolko=1000, potokov=8):
    os.environ.setdefault('XMLRIVER_CHANNELS', '8')
    import enrich_contacts as EC
    задачи, порог, всего_верх = цели(skolko)
    if not задачи:
        return {'нечего искать': True}
    итог = {'взято': len(задачи), 'нашли': 0, 'подтвердили': 0, 'в_кандидаты': 0,
            'не_нашли': 0, 'порог_выручки_млн': round(порог / 1e6, 1),
            'в_топ30': всего_верх}
    t0 = time.time()

    def одна(k):
        try:
            site, src, card = EC.find_site_via_xmlriver(k)
        except Exception as e:  # noqa: BLE001
            return {'inn': k['inn'], 'site': None, 'src': 'сбой:%s' % str(e)[:50]}
        if not site:
            return {'inn': k['inn'], 'site': None, 'src': src}
        # ПРОВЕРКА: открываем и ищем ИНН или имя
        vердикт = ''
        try:
            html, _sp, _m = EC._fetch_site(site)
        except Exception:  # noqa: BLE001
            html = ''
        if html:
            if k['inn'] in re.sub(r'\D', '', html):
                vердикт = 'xmlriver+инн-на-сайте'
            else:
                сл = _slova(k['name'])
                h = html.upper()
                if сл and sum(1 for w in сл if w in h) >= max(1, len(сл) // 2):
                    vердикт = 'xmlriver+имя-на-сайте'
        return {'inn': k['inn'], 'name': k['name'][:60], 'site': site, 'src': src,
                'verdikt': vердикт}

    with ThreadPoolExecutor(max_workers=potokov) as ex:
        rez = list(ex.map(одна, задачи))

    with open(LOG, 'a', encoding='utf-8') as f:
        for r in rez:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

    c = sqlite3.connect(BD, timeout=60)
    try:
        c.execute('ALTER TABLE companies ADD COLUMN site_source TEXT')
    except Exception:  # noqa: BLE001
        pass
    for r, k in zip(rez, задачи):
        if not r.get('site'):
            итог['не_нашли'] += 1
            continue
        итог['нашли'] += 1
        есть = c.execute('select 1 from companies where inn=?', (r['inn'],)).fetchone()
        if not есть:
            c.execute("INSERT INTO companies(inn, name, region, updated_at) VALUES(?,?,?,?)",
                      (r['inn'], k['name'][:200], k['city'][:80],
                       time.strftime('%Y-%m-%dT%H:%M:%S')))
        if r.get('verdikt'):
            c.execute('update companies set site=?, site_source=?, updated_at=? where inn=?',
                      (r['site'], r['verdikt'], time.strftime('%Y-%m-%dT%H:%M:%S'), r['inn']))
            итог['подтвердили'] += 1
        else:
            c.execute("update companies set cand_site=?, updated_at=? where inn=? "
                      "and coalesce(site,'')=''",
                      (r['site'], time.strftime('%Y-%m-%dT%H:%M:%S'), r['inn']))
            итог['в_кандидаты'] += 1
    c.commit()
    c.close()
    итог['секунд'] = round(time.time() - t0)
    итог['рублей_примерно'] = round(len(задачи) * 25 / 1000, 1)
    return итог


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    p = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    print(json.dumps(прогон(n, p), ensure_ascii=False))
