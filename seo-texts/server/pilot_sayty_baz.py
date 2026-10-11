# -*- coding: utf-8 -*-
r"""Сайты-кандидаты из НАШИХ баз для компаний, у которых сайт отклонён, не найден или это визитка (11.10, ревизия-2:
2-06 №3 — у 986 компаний «сайт отклонён, 0 контактов» другой кандидат есть в обзвоне/enrich/Checko и не проверялся,
сильный у 408; 2-09 Н3 — домен корпоративной почты из базы (Колви → kolvy.ru, ОЗСК → ozsk.ru); 2-10 №1 — визитки
Яндекс Бизнеса *.clients.site у 62 компаний, у 29 настоящий сайт в базах).

Кандидаты: sites базы обзвона, enrich companies.site/cand_site, requisites.site_checko, домены корпоративных почт
(обзвон, Checko). Без провайдеров почты, площадок/соцсетей (ploshchadki), доменов на ≥3 ИНН, отклонённого домена.
Проверка — sayt_po_nazvaniyu.проверить (главная: ИНН, название; при неясности — модель по главной). Принимаем: ИНН или
название на главной, «модель: сайт компании», «домен похож» — только при ≥2 источниках или домене почты.
Принятый — в <набор>-spisok.json (сайт_был, сайт_откуда), под замком; дальше обычная цепочка: обход видит смену сайта и
обходит заново, затем роли, «чей номер», проверка сайта. Журнал проверок — <набор>-sayty-baz.jsonl (fsync, резюм).
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
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_pochty as KP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import ploshchadki as PL  # noqa: E402
import sayt_po_nazvaniyu as SN  # noqa: E402
import zamok  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
СПИСОК = os.path.join(DIR, НАБОР + '-spisok.json')
ЖУРНАЛ = os.path.join(DIR, НАБОР + '-sayty-baz.jsonl')
ВИЗИТКИ = ('clients.site', 'taplink.ws', 'taplink.cc', 'tilda.ws', 'wixsite.com', 'mya5.ru', 'business.site')
ПРОВАЙДЕРЫ = set(KP.ПУБЛИЧНЫЕ) | {'yandex.by', 'mail.ua', 'ukr.net', 'tut.by', 'rambler.ru', 'ya.ru', 'gmail.ru', 'yndex.ru',
                                 'brest.by', 'vitebsk.by', 'gomel.by', 'grodno.by', 'mogilev.by', 'minsk.by', 'open.by', 'bk.ru'}
_лок = threading.Lock()


def визитка(с):
    х = MN.домен(с or '')
    хп = re.sub(r'^\w+://', '', (с or '').lower()).split('/')[0]
    return any(хп.endswith(в) for в in ВИЗИТКИ) or х in ВИЗИТКИ


def годный_домен(д):
    return bool(д) and '.' in д and д not in ПРОВАЙДЕРЫ and not PL.из_списка(д) and not визитка(д)


def записать(з):
    with _лок:
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(СПИСОК, encoding='utf-8'))['компании']
    посл = {}
    with open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), 'rb') as f:
        for s in f:
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('inn') in сп:
                посл[з['inn']] = з
    пров, опров = {}, {}
    for ф, куда in (('-sayt-proverka.jsonl', пров), ('-oprov.jsonl', опров)):
        п = os.path.join(DIR, НАБОР + ф)
        if os.path.exists(п):
            for s in io.open(п, encoding='utf-8', errors='replace'):
                try:
                    x = json.loads(s)
                    куда[x['inn']] = x
                except (ValueError, KeyError):
                    pass
    сделано = set()
    if os.path.exists(ЖУРНАЛ):
        for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['inn'])
            except (ValueError, KeyError):
                pass
    # кому нужен другой сайт
    нужны = {}
    for i, к in сп.items():
        if not i.isdigit() or i in сделано:
            continue
        сайт = к.get('сайт') or ''
        з = посл.get(i) or {}
        дом = MN.домен(сайт)
        инн_на = i in (з.get('инн_живой') or [])
        плохой = (not сайт or визитка(сайт) or
                  ((пров.get(i) or {}).get('итог') == 'другая' and MN.домен((пров[i].get('сайт') or '')) == дом and not инн_на) or
                  ((опров.get(i) or {}).get('итог') == 'опровергаю' and MN.домен(опров[i].get('сайт') or '') == дом and not инн_на
                   and (пров.get(i) or {}).get('итог') not in ('та же', 'группа')) or
                  (з.get('итог') == 'ok' and not any(ст in ('ok', 'кэш') for _, ст in з.get('страницы') or [])))
        if плохой:
            нужны[i] = дом
    # кандидаты из баз
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    канд = collections.defaultdict(lambda: collections.defaultdict(set))
    частота = collections.Counter()
    инны = list(нужны)
    for k in range(0, len(инны), 500):
        ч = инны[k:k + 500]
        м = ','.join('?' * len(ч))
        for inn, sites, em in c.execute('select inn, coalesce(sites,""), coalesce(emails_base,"") from obz.obzvon '
                                        'where inn in (%s)' % м, ч):
            for x in re.split(r'[\s,;|]+', sites):
                if '.' in x:
                    канд[str(inn)][MN.домен(x)].add('обзвон')
            for x in em.split('|'):
                if '@' in x:
                    канд[str(inn)][MN.домен(x.split('@')[-1])].add('почта обзвона')
        for inn, site, cs in c.execute('select inn, coalesce(site,""), coalesce(cand_site,"") from companies where inn in (%s)' % м, ч):
            for x, ист in ((site, 'enrich'), (cs, 'enrich-кандидат')):
                if '.' in (x or ''):
                    канд[str(inn)][MN.домен(x)].add(ист)
        for inn, sc, ec in c.execute('select inn, coalesce(site_checko,""), coalesce(emails_checko,"") from requisites '
                                     'where inn in (%s)' % м, ч):
            if '.' in sc:
                канд[str(inn)][MN.домен(sc)].add('checko')
            for x in ec.split('|'):
                if '@' in x:
                    канд[str(inn)][MN.домен(x.split('@')[-1])].add('почта checko')
    for inn, sites in c.execute('select inn, coalesce(sites,"") from obz.obzvon where coalesce(sites,"")<>""'):
        for x in {MN.домен(y) for y in re.split(r'[\s,;|]+', sites) if '.' in y}:
            частота[x] += 1
    c.close()
    задачи = []
    for i, дом in нужны.items():
        вар = [(д, и) for д, и in канд.get(i, {}).items() if годный_домен(д) and д != дом and частота[д] < 3]
        вар.sort(key=lambda x: (-len(x[1]), not any('почта' in y for y in x[1])))
        for д, и in вар[:2]:
            задачи.append((i, д, sorted(и)))
    задачи.sort(key=lambda x: -(сп[x[0]].get('выручка') or 0))
    print('нужен другой сайт', len(нужны), 'с кандидатами', len({x[0] for x in задачи}), 'проверок', len(задачи), flush=True)
    принято = {}

    def проверка(x):
        i, д, ист = x
        if i in принято:
            return
        к = сп[i]
        try:
            ок, почему = SN.проверить(к.get('имя') or '', i, 'https://' + д, регион=к.get('регион') or '', сегм=к.get('сегм') or '')
        except Exception as e:  # noqa: BLE001
            ок, почему = False, 'сбой: ' + repr(e)[:80]
        сильный = len(ист) >= 2 or any('почта' in y for y in ист)
        взять = ок and (not почему.startswith('домен похож') and not почему.startswith('главная не открылась') or сильный)
        записать({'inn': i, 'сайт': д, 'источники': ист, 'проверка': почему, 'принят': bool(взять), 'был': нужны[i],
                  'ts': time.strftime('%Y-%m-%dT%H:%M:%S')})
        if взять:
            with _лок:
                принято.setdefault(i, (д, '; '.join(ист), почему))

    with ThreadPoolExecutor(int(os.environ.get('KC_POTOKOV_SHAGA', '16'))) as ex:
        list(ex.map(проверка, задачи))
    if принято:
        with zamok.замок(СПИСОК):
            сп2 = zamok.прочитать(СПИСОК)
            n = 0
            for i, (д, ист, почему) in принято.items():
                к = сп2['компании'].get(i)
                if not к or MN.домен(к.get('сайт') or '') == д:
                    continue
                к['сайт_был'] = к.get('сайт') or ''
                к['сайт'] = 'https://' + д
                к['сайт_откуда'] = 'наша база (%s): %s' % (ист, почему[:100])
                n += 1
            if n:
                shutil.copyfile(СПИСОК, СПИСОК + '.bak-' + time.strftime('%d%m-%H%M'))
                zamok.записать_атомарно(СПИСОК, сп2)
        shutil.copyfile(СПИСОК, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(СПИСОК)))
    print('===ИТОГ===')
    print('готово', json.dumps({'нужен сайт': len(нужны), 'проверок': len(задачи), 'принято': len(принято),
                                 'по причине': collections.Counter(p.split(' ')[0] for _, _, p in принято.values())},
                                ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
