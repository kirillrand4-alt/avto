# -*- coding: utf-8 -*-
"""fixD: скачать страницы-источники номеров и сайты компаний панели Meyer для проверки «чей сайт».

Локально (песочница, через прокси сессии), бережно: по одному запросу на домен за раз, пауза
между страницами домена, параллельно – разные домены. Уже скачанное не качается (кэш в папке).
Что качается по каждой компании: все ссылки-источники номеров (кроме площадок закупок и
агрегаторов выписок) + главная `sayt`; затем по каждому домену – до 5 страниц «контакты /
реквизиты / о компании / раскрытие информации», найденных по ссылкам с уже скачанных страниц.

    python3 fixD_kachat.py <каталог.db> <папка-кэша> [--potokov 12]
"""
import gzip
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import requests

BAZA, PAPKA = sys.argv[1], sys.argv[2]
POTOKOV = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 12
os.makedirs(PAPKA, exist_ok=True)
INDEKS = os.path.join(PAPKA, '_indeks.json')
CA = '/root/.ccr/ca-bundle.crt'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')
NE_SAYTY = ('zakupki.gov.ru', 'tender.pro', 'b2b-center.ru', 'rts-tender.ru', 'sberbank-ast.ru', 'roseltorg.ru',
            'fabrikant.ru', 'etp-ets.ru', 'tektorg.ru', 'otc.ru', 'zakazrf.ru', 'etpgpb.ru', 'lot-online.ru',
            'onlinecontract.ru', 'bidzaar.com', 'tenderguru.ru', 'rostender.info', 'b2b-energo.ru',
            'gazneftetorg.ru', 'etprf.ru', 'zakupki.rosatom.ru', 'tenderplan.ru', 'zakupki.mos.ru', 'torgi.gov.ru',
            'checko.ru', 'inndex.ru', 'companies.rbc.ru', 'b2book.ru', 'b2b.house', 'companium.ru',
            'zachestnyibiznes.ru', 'star-pro.ru', 'ofcheck.ru', 'credinform', 'rusprofile', 'list-org.com',
            'sbis.ru', 'saby.ru', 'audit-it.ru', 'vk.com', 't.me', 'ok.ru', 'youtube.com', 'hh.ru')
KLYUCH = re.compile(r'контакт|реквизит|о компании|о нас|о предприятии|о заводе|компания|раскрыт|юридическ|'
                    r'contact|rekvizit|requisit|about|kontakt|o-kompanii|o-nas|company|info|raskryt|disclos',
                    re.I)


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    d = d[4:] if d.startswith('www.') else d
    if any(ord(c) > 127 for c in d):
        try:
            d = d.encode('idna').decode('ascii')
        except UnicodeError:
            pass
    return d if '.' in d else ''


def ne_sayt(d):
    return any(d == x or d.endswith('.' + x) or x in d for x in NE_SAYTY)


def imya(url):
    return hashlib.sha1(url.encode('utf-8')).hexdigest()[:20] + '.html.gz'


lok = threading.Lock()
indeks = json.load(open(INDEKS, encoding='utf-8')) if os.path.exists(INDEKS) else {}


def sohranit_indeks():
    with lok:
        tmp = INDEKS + '.tmp'
        json.dump(indeks, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, INDEKS)


def vzyat(ses, url):
    if url in indeks and indeks[url].get('kod') is not None:
        return indeks[url]
    zap = {'kod': None, 'fajl': '', 'itog': '', 'oshibka': ''}
    varianty = [url]
    if url.startswith('https://'):
        varianty.append('http://' + url[8:])
    for v in varianty:
        try:
            r = ses.get(v, timeout=(10, 25), allow_redirects=True, verify=CA, stream=True)
            telo = b''
            for kus in r.iter_content(65536):
                telo += kus
                if len(telo) > 4_000_000:
                    break
            r.close()
            zap = {'kod': r.status_code, 'itog': r.url, 'oshibka': '', 'tip': r.headers.get('content-type', ''),
                   'kodirovka': r.encoding or '', 'dlina': len(telo), 'fajl': imya(url)}
            with gzip.open(os.path.join(PAPKA, zap['fajl']), 'wb') as f:
                f.write(telo)
            break
        except Exception as e:  # noqa: BLE001
            zap = {'kod': -1, 'fajl': '', 'itog': '', 'oshibka': repr(e)[:200]}
    with lok:
        indeks[url] = zap
    return zap


def tekst(zap):
    if not zap.get('fajl'):
        return ''
    b = gzip.open(os.path.join(PAPKA, zap['fajl'])).read()
    m = re.search(rb'charset=["\']?([\w-]+)', b[:3000])
    kod = (m.group(1).decode('ascii', 'ignore') if m else '') or zap.get('kodirovka') or 'utf-8'
    try:
        return b.decode(kod, 'replace')
    except LookupError:
        return b.decode('utf-8', 'replace')


def ssylki(html, baza, d):
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        href, txt = m.group(1).strip(), re.sub(r'<[^>]+>|\s+', ' ', m.group(2)).strip()
        if href.startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        u = urljoin(baza, href)
        if domen(u) != d or re.search(r'\.(pdf|jpe?g|png|docx?|xlsx?|zip|rar)(\?|$)', u, re.I):
            continue
        if KLYUCH.search(txt) or KLYUCH.search(urlsplit(u).path):
            out.append(u.split('#')[0])
    return list(dict.fromkeys(out))


def po_domenu(d, urls, ses):
    for u in urls:
        vzyat(ses, u)
        time.sleep(0.7)
    dop = []
    for u in urls:
        z = indeks.get(u) or {}
        if z.get('kod') == 200:
            dop += ssylki(tekst(z), z.get('itog') or u, d)
    dop = [u for u in dict.fromkeys(dop) if u not in urls][:5]
    for u in dop:
        vzyat(ses, u)
        time.sleep(0.7)
    return d


def glavnaya():
    import sqlite3
    k = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
    po_dom = {}
    for inn, sayt in k.execute('select inn, sayt from company'):
        for s in re.split(r'[\s,;]+', sayt or ''):
            d = domen(s)
            if d and not ne_sayt(d):
                po_dom.setdefault(d, set()).add('https://%s/' % d if not s.startswith('http') else
                                                 '%s://%s/' % (s.split('://')[0], urlsplit(s).netloc))
    for inn, su in k.execute('select inn, source_url from contact'):
        for u in (su or '').replace(';', ' ').split():
            d = domen(u)
            if u.startswith('http') and d and not ne_sayt(d):
                po_dom.setdefault(d, set()).add(u)
                po_dom[d].add('%s://%s/' % (u.split('://')[0], urlsplit(u).netloc))
    print('доменов: %d, адресов: %d' % (len(po_dom), sum(len(v) for v in po_dom.values())), flush=True)
    t0 = time.time()
    gotovo = [0]

    def rab(item):
        d, urls = item
        ses = requests.Session()
        ses.headers.update({'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'})
        try:
            po_domenu(d, sorted(urls), ses)
        except Exception as e:  # noqa: BLE001
            print('ОШИБКА', d, repr(e)[:200], flush=True)
        with lok:
            gotovo[0] += 1
            n = gotovo[0]
        if n % 40 == 0:
            sohranit_indeks()
            print('%d/%d доменов, %d с' % (n, len(po_dom), time.time() - t0), flush=True)

    with ThreadPoolExecutor(POTOKOV) as ex:
        list(ex.map(rab, sorted(po_dom.items())))
    sohranit_indeks()
    kody = {}
    for z in indeks.values():
        kody[str(z.get('kod'))] = kody.get(str(z.get('kod')), 0) + 1
    print('готово за %d с; коды: %s' % (time.time() - t0, kody))


POLITIKA = re.compile(r'политик|конфиденциальн|персональн|соглашени|оферт|privacy|policy|politika|konfid|'
                      r'personal|soglash|oferta|agreement|terms', re.I)
UGADAT = ('contacts/', 'kontakty/', 'contact/', 'rekvizity/', 'requisites/', 'about/', 'o-kompanii/',
          'policy/', 'privacy/', 'politika-konfidencialnosti/')


def dobavka(spisok_domenov):
    """Второй проход для неопределённых доменов: ссылки на политику/оферту/реквизиты со всех уже
    скачанных страниц домена + угаданные пути (до 10 запросов на домен)."""
    t0 = time.time()

    def rab(d):
        ses = requests.Session()
        ses.headers.update({'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'})
        est = [u for u, z in list(indeks.items()) if domen(u) == d]
        ok = [u for u in est if (indeks.get(u) or {}).get('kod') == 200]
        baza = None
        for u in ok:
            z = indeks[u]
            baza = baza or ('%s://%s/' % ((z.get('itog') or u).split('://')[0], urlsplit(z.get('itog') or u).netloc))
        if not baza:
            baza = 'https://%s/' % d
        novye = []
        for u in ok:
            z = indeks[u]
            html = tekst(z)
            for m in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
                href, txt = m.group(1).strip(), re.sub(r'<[^>]+>|\s+', ' ', m.group(2))
                if href.startswith(('mailto:', 'tel:', 'javascript:')):
                    continue
                uu = urljoin(z.get('itog') or u, href).split('#')[0]
                if domen(uu) != d or re.search(r'\.(jpe?g|png|docx?|xlsx?|zip|rar)(\?|$)', uu, re.I):
                    continue
                if POLITIKA.search(txt) or POLITIKA.search(urlsplit(uu).path) or KLYUCH.search(txt):
                    novye.append(uu)
        novye = [u for u in dict.fromkeys(novye) if u not in est][:6]
        ugad = [urljoin(baza, p) for p in UGADAT if urljoin(baza, p) not in est and urljoin(baza, p) not in novye]
        for u in (novye + ugad)[:10]:
            vzyat(ses, u)
            time.sleep(0.5)
        return d

    with ThreadPoolExecutor(POTOKOV) as ex:
        list(ex.map(rab, spisok_domenov))
    sohranit_indeks()
    print('добавка: %d доменов за %d с' % (len(spisok_domenov), time.time() - t0))


if __name__ == '__main__':
    if '--dop' in sys.argv:
        dobavka([x.strip() for x in open(sys.argv[sys.argv.index('--dop') + 1], encoding='utf-8') if x.strip()])
    else:
        glavnaya()
