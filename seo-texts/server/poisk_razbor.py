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
# пилот 08.10: страниц каталогов в выдаче с листанием — 58 тыс. (≈9 ч разбора), большинство — СМИ, госсайты, маркетплейсы.
# Разбираем только полезные: справочники ИНН, белорусские справочники (УНП), B2B-каталоги (с лимитом на домен) и
# страницы с ИНН в адресе; остальные — пропуск.
КАТ_ИНН = re.compile(r'(rusprofile|checko|list-org|zachestnyibiznes|sbis|audit-it|companies\.rbc|testfirm|spark-interfax|'
                     r'kontur|focus\.|vbankcenter|kartoteka|ofdata|egrul|bo\.nalog|e-ecolog|synapsenet|rusprofile|'
                     r'checko|innproverka|companium|rbc\.ru/companies|sravni|bankrot)', re.I)
КАТ_BY = re.compile(r'(belarusinfo\.by|ibiz\.by|b2b\.by|ex\.by|kompass|bizinfo\.by|egr\.gov\.by|kartoteka\.by|'
                    r'buybelarus|deal\.by|flagma\.by|belpromportal|catalog\.by)', re.I)
КАТ_B2B = re.compile(r'(agroserver|regtorg|productcenter|pulscen|производитель|xn--|fabricators|promportal|bizorg|zol\.ru|'
                     r'all\.biz|tiu\.ru|satu|orgpage|spravker|selhozproizvoditeli|milknet|meatinfo|exportcenter|'
                     r'clients\.site|b2b|agrobase|agroru|unipack|plastinfo|plastics|rcycle|vtorothodi|vtorbiz)', re.I)
ЛИМИТ_B2B_ДОМЕН = int(os.environ.get('POISK_LIMIT_B2B', '40'))
ЛИМИТ_ИНН_ДОМЕН = int(os.environ.get('POISK_LIMIT_INN', '60'))
# 09.10, проба meyer7t (владелец: «не скачивать домены, которые стабильно отказывают, если отказы даже через браузер»).
# Проверка _katalogi_brauzer.py: отказывают и обычному браузеру — rbc (401), companium (429+капча), list-org, agroserver,
# audit-it, testfirm (сброс соединения), zakupki.kontur (403), b2b-postavki (капча), plastinfo (403); открываются, но
# ИНН/УНП не дают ни разу — orgpage, belarusinfo, flagma, ibiz, bizorg, agroru, b2b.by, e-kontur. checko и b2b.house
# отдают страницы только браузеру (скрипту 429 / ИНН только после JS) — их страницы разбирает razbor_brauzer.py.
# Страницы с ИНН в адресе берутся и с этих доменов (не скачиваются). Включается POISK_KAT_STOP=1.
КАТ_СТОП = re.compile(r'(^|\.)(companies\.rbc\.ru|companium\.ru|list-org\.com|agroserver\.ru|audit-it\.ru|testfirm\.ru|'
                      r'zakupki\.kontur\.ru|b2b-postavki\.ru|plastinfo\.ru|orgpage\.(ru|by)|belarusinfo\.by|flagma\.by|'
                      r'ibiz\.by|bizorg\.su|agroru\.com|b2b\.by|e-kontur\.ru)$', re.I)
КАТ_БРАУЗЕР = re.compile(r'(^|\.)(checko\.ru|b2b\.house)$', re.I)
СТОП_ВКЛ = os.environ.get('POISK_KAT_STOP') == '1'
# Свой напор банит сервер (audit-it, testfirm, orgpage отдали часть страниц, через минуту — сброс соединения и браузеру):
# не больше POISK_KAT_NA_DOMEN одновременных запросов к одному каталогу; POISK_KAT_PREDOHR отказов подряд — страницы
# домена до конца запуска пропускаются (не пишутся: следующий запуск попробует снова). 0 — выключено.
НА_ДОМЕН = int(os.environ.get('POISK_KAT_NA_DOMEN', '0'))
ПРЕДОХР = int(os.environ.get('POISK_KAT_PREDOHR', '0'))
_сем, _сем_лок = {}, threading.Lock()
_подряд, _выкл = collections.Counter(), set()


def семафор(д):
    with _сем_лок:
        if д not in _сем:
            _сем[д] = threading.BoundedSemaphore(НА_ДОМЕН or 10000)
        return _сем[д]


def по_кругу(урлы):
    """Страницы каталогов вперемешку по доменам: подряд в очереди не стоят десятки страниц одного каталога
    (иначе потоки пула ждут его семафор)."""
    по_дом = collections.OrderedDict()
    for u in урлы:
        по_дом.setdefault(MN.домен(хост(u)), []).append(u)
    out = []
    while по_дом:
        for д in list(по_дом):
            out.append(по_дом[д].pop(0))
            if not по_дом[д]:
                del по_дом[д]
    return out


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


# 10.10, ревизия meyer7: домены второго уровня у платформ/региональных зон (spb.ru, narod.ru, tilda.ws…) —
# у каждого поддомена свой владелец; считать их одним «доменом» = записывать сотни сайтов в агрегатор.
ПЛАТФОРМЫ = re.compile(r'\.(spb|msk|nov|nnov|ekb|kiev|com|net|org|pp|biz|ru|by|of|edu|narod|ucoz|ucoz\.net|at\.ua|'
                       r'tilda|turbo|wix|wixsite|webflow|nethouse|umi|ukit|ru\.net|mya5|okis|jimdo|uralweb|'
                       r'clients|business|site|flagma|satu|deal|tiu|all\.biz|blogspot|livejournal|github)'
                       r'\.(ru|ws|com|site|by|kz|ua|io|me|net|su|ru\.com|biz)$', re.I)


def кор_дом(h):
    ч = (h or '').split('.')
    if len(ч) >= 3 and ПЛАТФОРМЫ.search('.' + '.'.join(ч[-2:])):
        return '.'.join(ч[-3:])
    return MN.домен(h)


# Порог «агрегатор по выдаче»: poisk (КЦ 07.10) — >=6 регионов; пилот (3 региона) — все 3 или >=30 запросов;
# полные наборы (meyer7: 85+ регионов) — >=15 регионов или >=60 запросов (ревизия: пилотный порог на всей стране
# отсекал 1–2,5 тыс. сайтов производителей с федеральной выдачей).
МНОГО_РЕГ = int(os.environ.get('POISK_MNOGO_REG', '15'))
МНОГО_ЗАПР = int(os.environ.get('POISK_MNOGO_ZAPR', '60'))


def много_ли(регионы, запросы):
    if НАБОР == 'poisk':
        return len(регионы) >= 6
    if НАБОР.startswith('pilot'):
        return len(регионы - {''}) >= 3 or len(запросы) >= 30
    return len(регионы - {''}) >= МНОГО_РЕГ or len(запросы) >= МНОГО_ЗАПР


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
    if з['инн_url']:  # карточка компании с ИНН в адресе — скачивать незачем (пилот 08.10: скорость)
        з['страница'] = 'не скачивалась: ИНН в адресе'
        return з
    if СТОП_ВКЛ and КАТ_СТОП.search(з['домен']):
        з['страница'] = 'не скачивалась: домен в стоп-листе'
        return з
    if СТОП_ВКЛ and КАТ_БРАУЗЕР.search(з['домен']):
        з['страница'] = 'не скачивалась: только браузер (razbor_brauzer)'
        return з
    д = MN.домен(з['домен'])
    if д in _выкл:
        return None  # предохранитель: не пишем — следующий запуск попробует снова
    with семафор(д):
        ст, html, _ = MN.скачать(u)
    if ПРЕДОХР:
        with _сем_лок:
            _подряд[д] = 0 if ст == 'ok' else _подряд[д] + 1
            if _подряд[д] >= ПРЕДОХР and д not in _выкл:
                _выкл.add(д)
                print('предохранитель: %s — %d отказов подряд (%s), до конца запуска пропускается' % (д, ПРЕДОХР, ст[:40]),
                      flush=True)
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
            регионы_домена[кор_дом(h)].add(з['регион'])
            запросы_домена[кор_дом(h)].add(з['запрос'])
    for з in serp:
        for д in з.get('доки', []):
            h = хост(д['url'])
            if not h or НЕ_БРАТЬ.search(h):
                continue
            кор = кор_дом(h)
            много = много_ли(регионы_домена[кор], запросы_домена[кор])
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
    каталоги, пропуск, на_домен = [], 0, collections.Counter()
    for u in урлы_каталогов:
        if u in сделано:
            continue
        h = хост(u)
        путь = urllib.parse.unquote(u)
        if any(CO.инн_ок(x) for x in ИНН_URL.findall(путь)):
            каталоги.append(u)
        elif (КАТ_ИНН.search(h) or КАТ_BY.search(h)) and на_домен[MN.домен(h)] < ЛИМИТ_ИНН_ДОМЕН:
            на_домен[MN.домен(h)] += 1
            каталоги.append(u)
        elif КАТ_B2B.search(h) and на_домен[MN.домен(h)] < ЛИМИТ_B2B_ДОМЕН:
            на_домен[MN.домен(h)] += 1
            каталоги.append(u)
        else:
            пропуск += 1
    print('страниц каталогов к разбору', len(каталоги), 'пропущено (не справочники)', пропуск, flush=True)
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
        if з is not None:
            з['запросы'] = урлы_каталогов[u][:5]
            записать(з)
        n[0] += 1
        if n[0] % 200 == 0:
            print('разобрано %d за %d мин' % (n[0], (time.time() - t0) / 60), flush=True)

    потоков_кат = os.environ.get('POISK_RAZBOR_POTOKOV_KAT')
    if потоков_кат:
        # 09.10: сайты и каталоги — два пула одновременно (хвост медленных сайтов больше не держит каталоги),
        # каталоги — своим числом потоков и вперемешку по доменам
        print('пулы: сайты %s, каталоги %s, на домен %s, предохранитель %s, стоп-лист %s' % (
            os.environ.get('POISK_RAZBOR_POTOKOV', '40'), потоков_кат, НА_ДОМЕН or '—', ПРЕДОХР or '—',
            'да' if СТОП_ВКЛ else 'нет'), flush=True)
        with ThreadPoolExecutor(int(os.environ.get('POISK_RAZBOR_POTOKOV', '40'))) as ex1, \
                ThreadPoolExecutor(int(потоков_кат)) as ex2:
            ф1 = ex1.map(шаг_сайт, сайты)
            ф2 = ex2.map(шаг_каталог, по_кругу(каталоги))
            list(ф1)
            list(ф2)
        if _выкл:
            print('выключены предохранителем:', ', '.join(sorted(_выкл)), flush=True)
    else:
        with ThreadPoolExecutor(int(os.environ.get('POISK_RAZBOR_POTOKOV', '40'))) as ex:
            list(ex.map(шаг_сайт, сайты))
            list(ex.map(шаг_каталог, каталоги))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-razbor.jsonl'))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
