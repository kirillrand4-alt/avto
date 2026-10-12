# -*- coding: utf-8 -*-
r"""Обход сайтов ПО ЛОГИКЕ КУБИКА ЗЕНКИ, но силами сервера (владелец 12.10: «ты сможешь посмотреть те же страницы,
что бы открывались? и проверить скорость, а для Зенки оставить только те, где защита стоит»).

Замер 12.10 на 300 сайтах из очереди Зенки: сервер ~3300 сайтов/ч (32 потока), Зенка ~420/ч; на ТРУДНЫХ сайтах (не
открылись при разборе выдачи) Зенка открыла 84%, сервер 22% — 403 (WAF по отпечатку), 503, SSL. Но 7800 из 8096 строк
очереди — сайты, которые у сервера УЖЕ открывались («контактов нет» / «только общие»): Зенка им нужна не открыть, а
пройти глубже. Это делает сервер: та же очередь страниц, что в кубике (C:\seostat\drop\zenno, obhod_stranic.cs):
  главная -> ссылки по весам (контакты; каталог/продукция; производство/оборудование; качество/лаборатория; экспорт;
  проекты/клиенты, руководство/филиалы, дилеры; новости; о компании) -> карта сайта (robots.txt -> Sitemap) ->
  угадки /contacts, /kontakty… (если контактной ссылки нет) -> до 18 страниц первого уровня (режим «oba») ->
  второй уровень под контактами/руководством и каталогом — до 12.
Годность страницы — порт pochemu_ne_godna кубика (заслон, 429, Cloudflare, антибот, пустая оболочка JS).

Выход — В ФОРМАТЕ КУБИКА в C:\seostat\drop\zenno\gotovo: <ключ>_N.html, затем .kanal.txt («сервер;oba;facts»),
.otkaz.txt, и последним .urls.txt; приёмник zenno_most --priyom разбирает их как страницы Зенки (кэш по ключу).
Главная не далась из-за защиты (403/429/503/Cloudflare/антибот/JS-оболочка/SSL/сброс соединения) — строка ВОЗВРАЩАЕТСЯ
в голову ochered.txt (Зенке); мёртвый домен (DNS), 404/410/5xx — не возвращается (Зенка тоже не откроет).
Журнал (резюм, fsync): meyer7-server-obhod.jsonl. Режимы:
  --zabrat   забрать из ochered.txt наши строки, чей сайт у сервера раньше открывался, в meyer7-server-ochered.txt;
  (без ключа) обойти meyer7-server-ochered.txt, пропуская уже сделанное по журналу.
"""
import csv
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
ZENNO = r'C:\seostat\drop\zenno'
GOTOVO = os.path.join(ZENNO, 'gotovo')
ОЧЕРЕДЬ = os.path.join(ZENNO, 'ochered.txt')
НАША = os.path.join(DIR, 'meyer7-server-ochered.txt')
ЖУРНАЛ = os.path.join(DIR, 'meyer7-server-obhod.jsonl')
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)

ПРЕДЕЛ = 12
ПЕРВЫЙ_УРОВЕНЬ = ПРЕДЕЛ + 6  # режим «oba» кубика: контакты И факты
СЛОВА = ('contact', 'kontakt', 'svyaz', 'about', 'o-kompanii', 'o-nas', 'company', 'rukovod', 'staff', 'team',
         'sotrudnik', 'rekvizit', 'filial', 'predstavitel', 'podrazdelen', 'otdel', 'office', 'ofis', 'adresa',
         'regiony', 'seti', 'vacan', 'career')
СЛОВА_ФАКТЫ = ('catalog', 'produk', 'tovar', 'assortiment', 'shop', 'price', 'prays', 'proizvod', 'production',
               'tehnolog', 'zavod', 'moshchnost', 'news', 'novosti', 'press', 'smi', 'blog', 'sobytiya', 'about',
               'o-kompanii', 'o-nas', 'company', 'history', 'kachestv', 'quality', 'sertifik', 'certificate', 'haccp',
               'uslugi', 'services', 'napravlen', 'reshen', 'solution', 'otrasl', 'primenen', 'industr', 'proekt',
               'project', 'obekt', 'portfolio', 'oborudovan', 'equipment', 'park', 'vacan', 'career', 'rabota', 'zakup',
               'postavshchik', 'tender', 'export', 'eksport', 'geografi', 'katalog', 'manufact', 'factory', 'laborator',
               'kontrol', 'certif', 'vneshneekon', 'zarubezh', 'sertifikaty', 'realizovan', 'vypolnen', 'nashi-raboty',
               'clients', 'klient', 'partner', 'diler', 'dealer')
СЛОВА_ОБА = tuple(dict.fromkeys(СЛОВА + СЛОВА_ФАКТЫ))
СЛОВА_КАРТЫ = ('catalog', 'katalog', 'produk', 'tovar', 'assortiment', 'proizvod', 'production', 'manufact', 'zavod',
               'tehnolog', 'kachestv', 'quality', 'sertifik', 'certif', 'laborator', 'export', 'eksport', 'zarubezh',
               'proekt', 'portfolio', 'obekt', 'realizovan', 'klient', 'partner', 'news', 'novosti', 'about',
               'o-kompanii', 'o-nas')
УГАДКИ = ('/contacts/', '/contacts', '/kontakty/', '/kontakty', '/contact/', '/contact', '/about/', '/about',
          '/o-kompanii/', '/o-kompanii', '/company/staff/', '/company/staff', '/company/', '/company',
          '/rukovodstvo/', '/rukovodstvo')
ВЕСА = ((0, ('contact', 'kontakt', 'svyaz')),
        (1, ('catalog', 'katalog', 'produk', 'tovar', 'assortiment', 'price', 'prays')),
        (2, ('proizvod', 'production', 'manufact', 'factory', 'zavod', 'tehnolog', 'moshchnost', 'oborudovan')),
        (3, ('kachestv', 'quality', 'sertifik', 'certif', 'laborator', 'kontrol', 'haccp')),
        (4, ('export', 'eksport', 'vneshneekon', 'zarubezh')),
        (5, ('proekt', 'project', 'portfolio', 'obekt', 'realizovan', 'vypolnen', 'nashi-raboty', 'clients', 'klient',
             'partner')),
        (5, ('rukovod', 'staff', 'otdel', 'filial')),
        (5, ('dealer', 'diler', 'geografi', 'regiony')),
        (6, ('news', 'novosti')),
        (7, ('about', 'o-kompanii', 'o-nas', 'company')))
HREF = re.compile(r'''href\s*=\s*["']([^"'#]{1,180})["']''', re.I)
ТЕХ = re.compile(r'wp-json|oembed|/feed|\?url=|print=|\.(xml|pdf|jpe?g|png)$', re.I)
# защита — ВЕРНУТЬ Зенке; прочее (DNS, 404, 5xx) — не возвращать
ЗАЩИТА_ОШИБКИ = re.compile(r'HTTP (403|429|503|401|406|444|520|521|522|523|525|526)|ssl|certificate|socket|timed? ?out|'
                           r'reset|remote ?disconnected|eof|connection ?(aborted|refused)', re.I)
МЁРТВЫЙ = re.compile(r'getaddrinfo|name or service|11001|11002|nodename', re.I)
# 12.10: почта — с ограниченной длиной и началом на границе токена. Было [\w.+-]+@ — на странице с base64-картинкой
# (сотни КБ без «@») перебор квадратичный, поток держит GIL, и весь обход вставал (48 потоков — темп падал, 96 — встал)
ПОЧТА = re.compile(r'(?<![\w.+-])[\w.+-]{1,64}@[\w-]{1,63}\.[a-z]{2,6}')
_лок = threading.Lock()


def почему_не_годна(h):
    """Порт pochemu_ne_godna кубика (пусто = годна) + маркеры антибота, которые у сервера встречаются чаще."""
    if not h or len(h) < 600:
        return 'пусто/обрывок'
    n = h.lower()
    м = re.search(r'<title[^>]*>(.*?)</title>', h, re.I | re.S)
    заг = м.group(1).lower() if м else ''
    короткая = len(h) < 8000
    if 'id="main-frame-error"' in n or 'neterror' in n or re.search(r'\bERR_[A-Z_]{3,}\b', h):
        return 'ошибка браузера'
    if len(h) > 50000:
        без = re.sub(r'<[^>]+>', ' ', re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h))
        if len(без.strip()) < 500:
            return 'пустая оболочка'
    if 'too many requests' in заг or '429' in заг or (короткая and re.search(
            r'too many requests|слишком много запросов|превышен лимит запросов', n)):
        return '429 лимит на адрес'
    if 'just a moment' in заг or 'attention required' in заг or (короткая and 'checking your browser' in n):
        return 'cloudflare'
    if короткая and re.search(r'are you not a robot|подтвердите, что вы человек|доступ ограничен|ddos-guard|__qrator|'
                              r'servicepipe|variti|captcha', n):
        return 'антибот'
    if короткая and ('403' in заг or '403 forbidden' in n):
        return '403'
    if короткая and ('404' in заг or 'не найдена' in заг):
        return '404'
    return ''


def ключ_ссылки(низ):
    for вес, слова in ВЕСА:
        if any(w in низ for w in слова):
            return вес
    return 9


def обойти(ключ, url):
    import meyer_nalichie as MN
    t0 = time.time()
    if not url.startswith('http'):
        url = 'http://' + url
    ст, главная, _ = MN.скачать(url)
    причина = (ст if ст != 'ok' else '') or почему_не_годна(главная)
    if причина:
        if МЁРТВЫЙ.search(причина):
            итог = 'мёртвый домен'
        elif ст == 'ok' or ЗАЩИТА_ОШИБКИ.search(причина):
            итог = 'защита -> Зенке'
        else:
            итог = 'не открылся'
        return {'ключ': ключ, 'url': url, 'итог': итог, 'причина': причина[:80], 'страниц': 0,
                'сек': round(time.time() - t0, 1)}
    база = urllib.parse.urlsplit(url)
    хост = база.hostname or ''
    корень = '%s://%s' % (база.scheme, база.netloc)
    адреса, htmly, отказы, видно = [url], [главная], [], {url}
    по_весу = [[] for _ in range(10)]
    for м in HREF.finditer(главная):
        с = м.group(1).strip()
        низ = с.lower()
        if not с or низ.startswith(('mailto:', 'tel:', 'javascript:')) or ТЕХ.search(низ):
            continue
        if not any(w in низ for w in СЛОВА_ОБА):
            continue
        try:
            полный = urllib.parse.urljoin(url, с)
        except ValueError:
            continue
        if urllib.parse.urlsplit(полный).hostname != хост or полный in видно:
            continue
        видно.add(полный)
        по_весу[ключ_ссылки(низ)].append(полный)
    сначала = [u for корз in по_весу for u in корз]
    # карта сайта: robots.txt -> Sitemap, иначе /sitemap.xml (до 3 карт, до 12 адресов по словарю фактов)
    карты, из_карты = [], []
    ст_r, роботс, _ = MN.скачать(корень + '/robots.txt')
    if ст_r == 'ok':
        карты = [s for s in re.findall(r'(?im)^\s*sitemap:\s*(\S+)', роботс) if s.startswith('http')][:5]
    if not карты:
        карты = [корень + '/sitemap.xml']
    k = 0
    while k < len(карты) and k < 3 and len(из_карты) < 12:
        ст_x, xml, _ = MN.скачать(карты[k])
        k += 1
        if ст_x != 'ok':
            continue
        for loc in re.findall(r'(?i)<loc>([^<]{1,300})</loc>', xml):
            loc = loc.strip()
            нл = loc.lower()
            if нл.endswith('.xml'):
                if loc not in карты and len(карты) < 5:
                    карты.append(loc)
                continue
            if any(w in нл for w in СЛОВА_КАРТЫ) and loc not in видно and len(из_карты) < 6:
                из_карты.append(loc)
    for u in из_карты:
        if u not in видно:
            видно.add(u)
            сначала.append(u)
    if not any(re.search(r'contact|kontakt', u.lower()) for u in сначала):
        for п in УГАДКИ:
            if корень + п not in видно:
                видно.add(корень + п)
                сначала.append(корень + п)
    второй = []
    взято = 0
    for u in сначала:
        if взято >= ПЕРВЫЙ_УРОВЕНЬ:
            break
        ст_, h, _ = MN.скачать(u)
        взято += 1
        отк = (ст_ if ст_ != 'ok' else '') or почему_не_годна(h)
        if отк:
            отказы.append('1|%s|%d|%s' % (отк[:40], len(h or ''), u))
            continue
        адреса.append(u)
        htmly.append(h)
        ну = u.lower()
        под_контактами = any(w in ну for w in ('contact', 'kontakt', 'staff', 'rukovod'))
        под_товаром = any(w in ну for w in ('catalog', 'katalog', 'produk', 'tovar', 'assortiment', 'proizvod'))
        if not (под_контактами or под_товаром):
            continue
        for м in HREF.finditer(h):
            с = м.group(1).strip()
            нс = с.lower()
            if not с or нс.startswith(('mailto:', 'tel:', 'javascript:')) or ТЕХ.search(нс):
                continue
            try:
                п2 = urllib.parse.urljoin(u, с)
            except ValueError:
                continue
            ок = any(w in нс for w in (СЛОВА_ОБА if под_товаром else СЛОВА)) or \
                (под_товаром and п2.lower().startswith(ну) and len(п2) > len(ну) + 3)
            if ок and urllib.parse.urlsplit(п2).hostname == хост and п2 not in видно:
                видно.add(п2)
                второй.append(п2)
    # СВЕРХ КУБИКА (владелец 12.10, as-agro.ru: почта на страницах направлений «птицефабрика», «переработка», а их
    # имена не из словаря — кубик их тоже не берёт): мало страниц и ни одной почты — любые внутренние ссылки главной
    if len(htmly) <= 2 and not ПОЧТА.search(' '.join(htmly).lower()):
        прочие = []
        for м in HREF.finditer(главная):
            с = м.group(1).strip()
            нс = с.lower()
            if not с or нс.startswith(('mailto:', 'tel:', 'javascript:')) or ТЕХ.search(нс) or '?' in нс:
                continue
            try:
                п3 = urllib.parse.urljoin(url, с)
            except ValueError:
                continue
            if urllib.parse.urlsplit(п3).hostname == хост and urllib.parse.urlsplit(п3).path.strip('/') and п3 not in видно:
                видно.add(п3)
                прочие.append(п3)
        второй = прочие[:6] + второй
    for u in второй[:ПРЕДЕЛ]:
        ст_, h, _ = MN.скачать(u)
        отк = (ст_ if ст_ != 'ok' else '') or почему_не_годна(h)
        if отк:
            отказы.append('2|%s|%d|%s' % (отк[:40], len(h or ''), u))
            continue
        адреса.append(u)
        htmly.append(h)
    # запись в формате кубика: сперва html, потом канал/отказы, последним .urls.txt
    for i, h in enumerate(htmly):
        with io.open(os.path.join(GOTOVO, '%s_%d.html' % (ключ, i)), 'w', encoding='utf-8') as f:
            f.write(h)
    with io.open(os.path.join(GOTOVO, '%s.kanal.txt' % ключ), 'w', encoding='utf-8') as f:
        f.write('сервер;oba;facts')
    if отказы:
        with io.open(os.path.join(GOTOVO, '%s.otkaz.txt' % ключ), 'w', encoding='utf-8') as f:
            f.write('\n'.join(отказы))
    with io.open(os.path.join(GOTOVO, '%s.urls.txt' % ключ), 'w', encoding='utf-8') as f:
        f.write('\n'.join(адреса))
    return {'ключ': ключ, 'url': url, 'итог': 'открыт', 'страниц': len(htmly), 'отказов': len(отказы),
            'почт': len(set(ПОЧТА.findall(' '.join(htmly).lower()))),
            'сек': round(time.time() - t0, 1)}


def в_голову_очереди(строки):
    """Строки -> в начало ochered.txt (Зенке). Кубик сам переписывает файл при взятии строки — проверяем, что легло."""
    if not строки:
        return 0
    for _ in range(6):
        было = [y for y in io.open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace').read().splitlines() if y.strip()]
        наши = {y.split(';')[0] for y in строки}
        было = [y for y in было if y.split(';')[0] not in наши]
        with io.open(ОЧЕРЕДЬ + '.tmp', 'w', encoding='utf-8') as f:
            f.write('\n'.join(строки + было) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(ОЧЕРЕДЬ + '.tmp', ОЧЕРЕДЬ)
        time.sleep(3)
        теперь = io.open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace').read()
        легло = sum(1 for y in строки if y.split(';')[0] + ';' in теперь)
        if легло >= len(строки) - 2:
            return легло
    return легло


def забрать():
    """Наши строки очереди, чей сайт у сервера уже открывался, — из ochered.txt в meyer7-server-ochered.txt."""
    р = list(csv.reader(io.open(r'C:\seostat\drop\drop-storage\MEYER-7-zenka.csv', encoding='utf-8-sig'), delimiter=';'))
    iК, iД, iГ = р[0].index('ИНН / ключ'), р[0].index('Домен'), р[0].index('Где не открылся')
    карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    обр = {v: k for k, v in карта.items()}
    серверу = set()
    for x in р[1:]:
        кл = x[iК].strip() if x[iК].strip().isdigit() else обр.get(x[iК].strip() or ('РАЗБОР:' + x[iД].strip()))
        г = x[iГ]
        if кл and ('контактов не найдено' in г or 'контакт' in г and 'ЛПР не найден' in г):
            серверу.add(кл)
    for _ in range(6):
        было = [y for y in io.open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace').read().splitlines() if y.strip()]
        взять = [y for y in было if y.split(';')[0].strip() in серверу]
        оставить = [y for y in было if y.split(';')[0].strip() not in серверу]
        уже = set(io.open(НАША, encoding='utf-8').read().split('\n')) if os.path.exists(НАША) else set()
        with io.open(НАША, 'a', encoding='utf-8') as f:
            for y in взять:
                if y not in уже:
                    f.write(y + '\n')
            f.flush()
            os.fsync(f.fileno())
        with io.open(ОЧЕРЕДЬ + '.tmp', 'w', encoding='utf-8') as f:
            f.write('\n'.join(оставить) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(ОЧЕРЕДЬ + '.tmp', ОЧЕРЕДЬ)
        time.sleep(3)
        теперь = [y for y in io.open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace').read().splitlines() if y.strip()]
        if not any(y.split(';')[0].strip() in серверу for y in теперь):
            break
    print(json.dumps({'забрано серверу': len(взять), 'осталось Зенке': len(теперь),
                      'всего в серверной очереди': len(set(io.open(НАША, encoding='utf-8').read().split()))},
                     ensure_ascii=False), flush=True)


def main():
    if '--zabrat' in sys.argv:
        забрать()
        return
    сделано = set()
    if os.path.exists(ЖУРНАЛ):
        for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['ключ'])
            except (ValueError, KeyError):
                pass
    задачи = []
    for y in io.open(НАША, encoding='utf-8', errors='replace').read().splitlines():
        ч = y.split(';')
        if len(ч) >= 2 and ч[0] not in сделано and ч[0] not in {к for к, _ in задачи}:
            задачи.append((ч[0], ч[1]))
    print('к обходу', len(задачи), 'уже в журнале', len(сделано), flush=True)
    сч = {'открыт': 0, 'защита -> Зенке': 0, 'мёртвый домен': 0, 'не открылся': 0, 'страниц': 0, 'сбой': 0}
    зенке, t0, n = [], time.time(), [0]

    def шаг(кв):
        try:
            з = обойти(*кв)
        except Exception as e:  # noqa: BLE001
            з = {'ключ': кв[0], 'url': кв[1], 'итог': 'сбой', 'причина': repr(e)[:100], 'страниц': 0}
        with _лок:
            with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            сч[з['итог']] = сч.get(з['итог'], 0) + 1
            сч['страниц'] += з.get('страниц') or 0
            if з['итог'] == 'защита -> Зенке':
                зенке.append('%s;%s;oba' % (кв[0], кв[1]))
                if len(зенке) >= 25:
                    в_голову_очереди(зенке[:])
                    del зенке[:]
            n[0] += 1
            if n[0] % 100 == 0:
                мин = (time.time() - t0) / 60
                print(time.strftime('%H:%M:%S'), 'готово %d/%d' % (n[0], len(задачи)), json.dumps(сч, ensure_ascii=False),
                      '| %.0f сайтов/ч' % (n[0] / мин * 60), flush=True)

    with ThreadPoolExecutor(int(os.environ.get('ZS_POTOKOV', '48'))) as ex:
        list(ex.map(шаг, задачи))
    with _лок:
        в_голову_очереди(зенке)
    print('===ИТОГ===', json.dumps(dict(сч, минут=round((time.time() - t0) / 60, 1)), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
