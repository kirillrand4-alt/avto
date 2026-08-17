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
import ploshchadki as PL          # noqa: E402  (после правки sys.path)
import sverka_privyazki as SP     # noqa: E402

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


def _translit_imeni(imya):
    """Латинские написания ядра названия — чтобы «свой» домен узнавался."""
    ядро = SP._ядро(imya)
    return '|'.join(SP._варианты(ядро)) if ядро else ''


def _slova(imya):
    t = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|АКЦИОНЕРНОЕ ОБЩЕСТВО|'
               r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ)\s*', '',
               (imya or '').upper()).strip(' "«»')
    return [w for w in re.split(r'[\s"«»,\-]+', t) if len(w) > 3]


def цели(skolko, dolya=None):
    """База обзвона по убыванию выручки: у кого сайта нет нигде и кого ещё не искали.

    Доля была 30%: начинали с верха по выручке, чтобы проверить саму затею и не
    жечь деньги вслепую. Затея проверена — 29 пачек, 351 рубль, — и владелец
    17.08 сказал брать всех. Порядок остаётся по выручке: крупные ищутся первыми,
    и если прогон остановить, остановится он на менее ценных.
    """
    dolya = float(os.environ.get('POISK_DOLYA', '1.0')) if dolya is None else dolya
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
        # ПЛОЩАДКА — не сайт компании, и проверять её незачем: реестр контрагентов
        # печатает ИНН крупно и первым делом, то есть проходит нашу же жёсткую
        # улику лучше настоящего завода. Замер 16.08: 818 привязок в базе вели на
        # площадки, 421 из них — на check.tochka.com.
        если_площадка = PL.из_списка(site)
        if если_площадка:
            return {'inn': k['inn'], 'site': None, 'src': 'площадка: ' + если_площадка}
        # ПРОВЕРКА: открываем и ищем ИНН или имя
        vердикт = ''
        try:
            html, _sp, _m = EC._fetch_site(site)
        except Exception:  # noqa: BLE001
            html = ''
        if html:
            сл = _slova(k['name'])
            h = html.upper()
            имя_на_сайте = bool(сл and sum(1 for w in сл if w in h) >= max(1, len(сл) // 2))
            свой = имя_на_сайте or PL.домен(site).split('.')[0] in _translit_imeni(k['name'])
            отказ = PL.площадка(site, html, k['inn'], свой_домен_или_имя=свой)
            if отказ:
                return {'inn': k['inn'], 'site': None, 'src': отказ}
            if k['inn'] in re.sub(r'\D', '', html):
                vердикт = 'xmlriver+инн-на-сайте'
            elif имя_на_сайте:
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
    # ЗАСЛОН (владелец 17.08, «запускай 1,2,3», пункт 3): домен, уже привязанный
    # к ДРУГОМУ ИНН, кандидатом не берём — иначе вычищенные тёзки-прилипалы
    # (avtoschool-vektor.ru на 14 «Векторах») прилипают заново следующим же
    # обходом, и чистка мульти-ИНН доменов становится вечной. Исключение одно:
    # ИНН самой компании напечатан на страницах — сайт группы вправе держать
    # несколько юрлиц (каталоги с чужими ИНН отсеяны выше, PL.площадка).
    занятые = {}
    for _инн, _s, _cs in c.execute(
            "select inn, coalesce(site,''), coalesce(cand_site,'') from companies "
            "where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''"):
        for _u in (_s, _cs):
            _d = PL.домен(_u) if _u else ''
            if _d:
                занятые.setdefault(_d, set()).add(str(_инн))
    for r, k in zip(rez, задачи):
        if not r.get('site'):
            итог['не_нашли'] += 1
            continue
        _дом = PL.домен(r['site'])
        _чьи = занятые.get(_дом) or set()
        if _чьи - {r['inn']} and r.get('verdikt') != 'xmlriver+инн-на-сайте':
            итог['домен_занят'] = итог.get('домен_занят', 0) + 1
            r['site'], r['src'] = None, 'домен занят другим ИНН: ' + _дом
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


def всё(пачка=500, потоков=8, пауза=20):
    """Гнать пачку за пачкой, пока цели не кончатся.

    Владелец 16.08: «давай все компании, а то ты партиями запускаешь и засыпаешь».
    Режим жил ТОЛЬКО на сервере и не был закоммичен — 17.08 песочницу откатило, я
    выложил на сервер версию из репозитория, и она затёрла живой код: процесс стал
    падать на первом же аргументе («--vse» вместо числа), а сторож послушно
    поднимал его каждые десять минут. Поэтому режим здесь, в репозитории.
    """
    итог = {'пачек': 0, 'нашли': 0, 'подтвердили': 0, 'в_кандидаты': 0, 'рублей': 0.0}
    while True:
        r = прогон(пачка, потоков)
        if r.get('нечего искать'):
            итог['кончились_цели'] = True
            break
        итог['пачек'] += 1
        for k in ('нашли', 'подтвердили', 'в_кандидаты'):
            итог[k] += r.get(k, 0)
        итог['рублей'] += r.get('рублей_примерно', 0)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        time.sleep(пауза)
    print(json.dumps(итог, ensure_ascii=False), flush=True)
    return итог


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--vse':
        if len(a) > 3:
            os.environ['POISK_DOLYA'] = a[3]
        всё(int(a[1]) if len(a) > 1 else 500, int(a[2]) if len(a) > 2 else 8)
    else:
        n = int(a[0]) if a else 1000
        p = int(a[1]) if len(a) > 1 else 8
        print(json.dumps(прогон(n, p), ensure_ascii=False))
