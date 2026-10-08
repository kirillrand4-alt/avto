# -*- coding: utf-8 -*-
r"""Сбор с нуля, агент 2 — разбор выдачи (poisk-serp.jsonl) в кандидатов-юрлиц.

  * свой сайт предприятия (не агрегатор): главная + «реквизиты/контакты/о компании/политика»
    (до 4 страниц) -> ИНН с контрольной суммой (частота), ОГРН; без ИНН — домен ищется в нашей
    базе (companies.site / obzvon.sites);
  * каталог/рейтинг/справочник (агрегаторы, домены, что встречаются в выдаче многих регионов):
    ИНН/ОГРН из адреса страницы и со страницы (рядом со словом ИНН). Это только находка компаний —
    номера отсюда не берутся (правило владельца).
Выход (fsync, резюм по url): C:\sender\server\poisk-razbor.jsonl -> копия на дроп.
"""
import collections
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_nalichie as MN  # noqa: E402
import meyer_proverka as MP  # noqa: E402
import cc_obhod as CO  # noqa: E402
import enrich_contacts as EC  # noqa: E402

# POISK_NABOR: poisk — сбор КЦ 07.10; pilot — пилот плана Meyer 08.10 (вход <набор>-serp.jsonl)
НАБОР = os.environ.get('POISK_NABOR', 'poisk')
ВЫХОД = os.path.join(DIR, НАБОР + '-razbor.jsonl')
УНП_RX = re.compile(r'УНП\D{0,6}(\d{9})(?!\d)')
_лок = threading.Lock()
НЕ_БРАТЬ = re.compile(r'(^|\.)(yandex\.|ya\.ru|google\.|youtube\.|vk\.(com|ru)|ok\.ru|t\.me|telegram|dzen\.ru|'
                      r'wikipedia|avito|ozon\.|wildberries|market\.yandex|2gis|zoon\.|flamp|otzovik|irecommend|'
                      r'hh\.ru|superjob|rabota|trudvsem|pikabu|livejournal|instagram|facebook|rutube|mail\.ru$)', re.I)
КАТАЛОГ = re.compile(r'(rusprofile|checko|list-org|zachestnyibiznes|sbis|audit-it|companies\.rbc|testfirm|'
                     r'productcenter|milknet|selhozproizvoditeli|spark-interfax|kontur|focus\.|vbankcenter|'
                     r'kartoteka|rbc\.ru|ofdata|egrul|nalog|synapsenet|bo\.nalog|e-ecolog|orgpage|spravker|'
                     r'all\.biz|pulscen|tiu\.ru|satu|b2b|tender|zakupki|clients\.site|exportcenter|agroserver|'
                     r'meatinfo|milkbranch|dairynews|pivo|vinograd|kombikorm|expocentr|prodexpo|agroprodmash|'
                     r'rating|reyting|top100|ratings)', re.I)
ОГРН_RX = re.compile(r'(?<!\d)([15]\d{12})(?!\d)')
ИНН_URL = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def хост(u):
    h = (urllib.parse.urlsplit(u if '://' in u else 'http://' + u).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def инн_из(т):
    out = collections.Counter()
    for м in CO.ИНН_RX.finditer(т):
        if CO.инн_ок(м.group(1)):
            out[м.group(1)] += 1
    return out


ЮРИМЯ = re.compile(r'(?<![А-ЯЁа-яё])(ООО|АО|ПАО|ЗАО|ОАО|НАО|ЧУП|ЧПУП|УП|СООО|ИООО|ОДО|КУП|РУП|СПК)\s*[«"]\s*([^«»"]{2,60}?)\s*[»"]')
ТИПОВЫЕ = ('rekvizity', 'requisites', 'rekvizity-kompanii', 'contacts', 'kontakty', 'about', 'o-kompanii',
           'politika-konfidencialnosti', 'privacy', 'policy', 'privacy-policy')


def ядро(имя):
    return re.sub(r'\s+', ' ', re.sub(r'[«»"\'.,]', ' ', имя or '')).strip().lower()


def индекс_имён():
    """Ядро названия (в кавычках) -> ИНН из наших баз: опознание сайта по юрназванию."""
    import sqlite3
    инд = collections.defaultdict(set)
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    for i, н1, н2 in c.execute("select inn, coalesce(name,''), coalesce(short_name,'') from companies "
                               "union all select inn, coalesce(name_short,''), '' from obz.obzvon"):
        for н in (н1, н2):
            for кус in re.findall(r'[«"]+([^«»"]{2,})[»"]+', н or ''):
                я = ядро(кус)
                if len(я) >= 3:
                    инд[я].add(str(i))
    c.close()
    return инд


def сайт(дом, о, база, имена=None):
    старт = о['url'] if о['url'].startswith('http') else 'http://' + о['url']
    корень = '%s://%s/' % (urllib.parse.urlsplit(старт).scheme or 'http', urllib.parse.urlsplit(старт).netloc)
    очередь = [корень] + ([старт] if старт.rstrip('/') != корень.rstrip('/') else [])
    инн, огрн, заг, страниц = collections.Counter(), collections.Counter(), '', 0
    унп = collections.Counter()
    i = 0
    for п in ТИПОВЫЕ:
        u = корень + п
        if u not in очередь:
            очередь.append(u)
    юр = collections.Counter()
    while i < len(очередь) and страниц < 7 and i < 16:
        u = очередь[i]
        i += 1
        ст, html, загол = MN.скачать(u)
        if ст != 'ok':
            continue
        страниц += 1
        заг = заг or re.sub(r'\s+', ' ', загол or '')[:150]
        т = MP.в_текст(html)
        инн.update(инн_из(т))
        унп.update(УНП_RX.findall(т))
        for м in ЮРИМЯ.finditer(т):
            юр['%s «%s»' % (м.group(1), м.group(2).strip())] += 1
        if (инн or унп) and страниц >= 3:
            break
        for м in re.finditer(r'ОГРН\D{0,12}([15]\d{12})(?!\d)', т):
            огрн[м.group(1)] += 1
        if i == 1:
            for л in CO.ссылки(u, html):
                if re.search(r'rekvizit|реквизит|kontakt|contact|about|o-kompanii|о-компании|politik|privacy|'
                             r'konfidenc|персональн', urllib.parse.unquote(л), re.I) and л not in очередь:
                    очередь.append(л)
    из_базы = sorted(база.get(MN.домен(дом), []))[:5]
    по_имени = []
    for н, _ in юр.most_common(3):
        я = ядро(н.split('«', 1)[-1])
        if имена is not None and 0 < len(имена.get(я, ())) <= 3:
            по_имени += sorted(имена[я])
    return {'тип': 'сайт', 'домен': дом, 'url': корень, 'заголовок': заг, 'страниц': страниц,
            'инн': инн.most_common(6), 'огрн': огрн.most_common(3), 'инн_база': из_базы,
            'юримена': юр.most_common(3), 'инн_по_имени': по_имени[:4], 'унп': унп.most_common(4)}


def каталог(u):
    з = {'тип': 'каталог', 'url': u, 'домен': хост(u)}
    путь = urllib.parse.unquote(u)
    з['инн_url'] = [x for x in ИНН_URL.findall(путь) if CO.инн_ок(x)][:3]
    з['огрн_url'] = ОГРН_RX.findall(путь)[:3]
    ст, html, _ = MN.скачать(u)
    з['страница'] = ст
    if ст == 'ok':
        т = MP.в_текст(html)
        з['инн'] = [x for x, _ in инн_из(т).most_common(300)]
        з['огрн'] = list(dict.fromkeys(re.findall(r'ОГРН\D{0,12}([15]\d{12})(?!\d)', т)))[:300]
        з['унп'] = list(dict.fromkeys(УНП_RX.findall(т)))[:300]
    return з


def main():
    serp = [json.loads(s) for s in io.open(os.path.join(DIR, НАБОР + '-serp.jsonl'), encoding='utf-8', errors='replace')]
    for з in serp:
        з.setdefault('сегм', з.get('вид', ''))
    регионы_домена = collections.defaultdict(set)
    запросы_домена = collections.defaultdict(set)
    по_домену, урлы_каталогов = {}, {}
    for з in serp:
        for д in з.get('доки', []):
            h = хост(д['url'])
            if not h or НЕ_БРАТЬ.search(h):
                continue
            регионы_домена[MN.домен(h)].add(з['регион'])
            запросы_домена[MN.домен(h)].add(з['запрос'])
    for з in serp:
        for д in з.get('доки', []):
            h = хост(д['url'])
            if not h or НЕ_БРАТЬ.search(h):
                continue
            кор = MN.домен(h)
            # пилот — всего 3 региона: агрегатор = во всех регионах пилота или в >= 30 разных запросах
            много = (len(регионы_домена[кор]) >= 6 if НАБОР == 'poisk' else
                     len(регионы_домена[кор] - {''}) >= 3 or len(запросы_домена[кор]) >= 30)
            агрегатор = (КАТАЛОГ.search(h) or много or not EC._is_own_site('http://' + h))
            if агрегатор:
                урлы_каталогов.setdefault(д['url'], []).append((з['сегм'], з['регион'], з['запрос']))
            else:
                о = по_домену.setdefault(h, {'url': д['url'], 'запросы': [], 'сниппет': д.get('title', '')})
                if len(о['запросы']) < 8:
                    о['запросы'].append([з['сегм'], з['регион'], з['запрос']])
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
                сделано.add(x.get('домен') if x['тип'] == 'сайт' else x['url'])
            except (ValueError, KeyError):
                pass
    база = CO.домены_базы()
    имена = индекс_имён()
    сайты = [(h, о) for h, о in по_домену.items() if h not in сделано]
    каталоги = [u for u in урлы_каталогов if u not in сделано]
    print('сайтов', len(по_домену), 'каталожных страниц', len(урлы_каталогов), 'в очереди', len(сайты), len(каталоги), flush=True)
    t0 = time.time()
    n = [0]

    def шаг_сайт(x):
        h, о = x
        try:
            з = сайт(h, о, база, имена)
        except Exception as e:  # noqa: BLE001
            з = {'тип': 'сайт', 'домен': h, 'url': о['url'], 'ошибка': repr(e)[:100]}
        з['запросы'] = о['запросы']
        з['сниппет'] = о['сниппет']
        записать(з)
        n[0] += 1
        if n[0] % 200 == 0:
            print('разобрано %d за %d мин' % (n[0], (time.time() - t0) / 60), flush=True)

    def шаг_каталог(u):
        try:
            з = каталог(u)
        except Exception as e:  # noqa: BLE001
            з = {'тип': 'каталог', 'url': u, 'ошибка': repr(e)[:100]}
        з['запросы'] = урлы_каталогов[u][:5]
        записать(з)
        n[0] += 1
        if n[0] % 200 == 0:
            print('разобрано %d за %d мин' % (n[0], (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(24) as ex:
        list(ex.map(шаг_сайт, сайты))
        list(ex.map(шаг_каталог, каталоги))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-razbor.jsonl'))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
