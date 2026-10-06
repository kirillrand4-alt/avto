# -*- coding: utf-8 -*-
"""Домены компаний из открытых каталогов (istochniki_domenov.md, «Порядок использования», п. 1).
Без XMLRiver и LLM. Запуск на сервере отдельным процессом (pusk.py analiz-аналог: pusk.py kat).
Выход: KATALOGI.jsonl — {source, rubric, name, card, url, domain}; продолжение по card.

Источники: Экспоцентр (Продэкспо, wyst_id=171), productcenter.ru (пищевые и с/х рубрики),
Руспродсоюз, Российский зерновой союз (PDF), Агроэкспорт (региональные PDF-каталоги), produkt.by.
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import analiz as A  # noqa: E402
import obrabotka as O  # noqa: E402

OUT = os.path.join(A.OUT, 'KATALOGI.jsonl')
LOCK = threading.Lock()
SOC = re.compile(r'(vk\.com|vk\.ru|ok\.ru|t\.me|telegram|facebook|instagram|youtube|rutube|dzen|twitter|x\.com|'
                 r'linkedin|whatsapp|viber|google|yandex|jsdelivr|gstatic|cloudflare|mail\.ru|apple\.com|max\.ru)', re.I)
PC_RUB = re.compile(r'ori?ekh|iagod|yagod|frukt|ovosh|muk|krup|masl|konserv|sok|sakhar|krakhmal|korm|zern|semen|'
                    r'bakale|makaron|myod|med|sukhofrukt|zamorozh|plodoov|sielsk|selsk|rastenievod|moloch', re.I)
done = set()


def emit(rec):
    with LOCK:
        if rec['card'] in done:
            return
        done.add(rec['card'])
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def ext_links(doc, own):
    out = []
    for h in re.findall(r'href=["\'](https?://[^"\'#\s]+)', doc or ''):
        d = O.norm_domain(h)
        if d and d != own and not SOC.search(d) and d not in out:
            out.append(d)
    return out


def _fix(doc):
    """Сервер объявляет windows-1251, а отдаёт UTF-8 (Экспоцентр): чиним двойную перекодировку."""
    if doc and doc.count('Р') > 50 and ('Р°' in doc or 'Рѕ' in doc):
        try:
            return doc.encode('cp1251', 'ignore').decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            return doc
    return doc


def get(u, **kw):
    for i in range(3):
        st, fin, doc = A.get(u, timeout=30, limit=kw.get('limit', 3_000_000))
        if st and st < 500:
            return st, fin, _fix(doc)
        time.sleep(2 + 3 * i)
    return st, fin, doc


# --- Экспоцентр -------------------------------------------------------------------

def expocentr(wyst=171):
    base = 'https://catalog.expocentr.ru/'
    _, _, doc = get(f'{base}table.php?wyst_id={wyst}&info_id=0')
    ids = sorted(set(re.findall(r'stand_id=(\d+)', doc)))

    def one(sid):
        card = f'{base}catalog.php?wyst_id={wyst}&info_id=0&stand_id={sid}'
        if card in done:
            return
        st, _, d = get(card)
        if not st or st >= 400:
            return
        name = re.search(r'<h1[^>]*>(.*?)</h1>', d, re.S)
        site = re.search(r"'Сайт'\);\">\s*(https?://[^<\s]+)", d)
        city = re.search(r'(?:Страна|Город)\s*:\s*</dt>\s*<dd>([^<]{2,60})', d)
        dom = O.norm_domain(site.group(1)) if site else ''
        emit({'source': 'expocentr', 'rubric': (city.group(1).strip() if city else ''),
              'name': re.sub(r'<[^>]+>|\s+', ' ', name.group(1)).strip()[:150] if name else '',
              'card': card, 'url': site.group(1) if site else '', 'domain': dom})
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, ids))
    return len(ids)


# --- productcenter -----------------------------------------------------------------

def productcenter(max_cards=6000):
    base = 'https://productcenter.ru'
    _, _, doc = get(base + '/producers')
    rubs = sorted(set(u for u in re.findall(r'/producers/catalog-[\w-]+-\d+', doc) if PC_RUB.search(u)))
    cards = []
    for r in rubs:
        for pg in range(1, 60):
            st, _, d = get(base + r + (f'/page-{pg}' if pg > 1 else ''))
            if not st or st >= 400:
                break
            ids = list(dict.fromkeys(re.findall(r'/producers/(\d+)/[\w-]+', d)))
            new = [(i, r) for i in ids if (i, r) not in cards]
            if not new:
                break
            cards += new
            if len(cards) >= max_cards:
                break
        if len(cards) >= max_cards:
            break
    seen = set()

    def one(item):
        i, r = item
        card = f'{base}/producers/site/{i}'
        if card in done or i in seen:
            return
        seen.add(i)
        st, _, d = get(card, limit=300_000)
        ext = ext_links(d, 'productcenter.ru')
        emit({'source': 'productcenter', 'rubric': r.split('catalog-')[1], 'name': '', 'card': card,
              'url': '', 'domain': ext[0] if ext else ''})
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, cards))
    return len(cards)


# --- одностраничные источники ---------------------------------------------------------

def rusprod():
    u = 'https://rusprodsoyuz.ru/participants/'
    _, _, d = get(u)
    n = 0
    for dom in ext_links(d, 'rusprodsoyuz.ru'):
        emit({'source': 'rusprodsoyuz', 'rubric': '', 'name': '', 'card': u + '#' + dom, 'url': '', 'domain': dom})
        n += 1
    return n


def pdf_domains(url, source, rubric=''):
    import pypdf
    st, _, _ = A.get(url, limit=1)  # проверка доступности
    req = urllib.request.Request(url, headers={'User-Agent': A.UA})
    raw = urllib.request.urlopen(req, timeout=60, context=A._CTX).read()
    text = '\n'.join((p.extract_text() or '') for p in pypdf.PdfReader(io.BytesIO(raw)).pages)
    n = 0
    for m in re.finditer(r'(?:https?://)?(?:www\.)?([\w-]+(?:\.[\w-]+)*\.(?:ru|рф|su|com|net|org|by|kz|pro|info|biz))\b', text, re.I):
        dom = O.norm_domain(m.group(1))
        if dom and not SOC.search(dom):
            emit({'source': source, 'rubric': rubric, 'name': '', 'card': url + '#' + dom, 'url': '', 'domain': dom})
            n += 1
    return n


def grun():
    _, _, d = get('https://grun.ru/membership/spisok_chlenov_rzs.php')
    pdfs = [urllib.parse.urljoin('https://grun.ru/', urllib.parse.quote(p, safe='/:')) for p in re.findall(r'href=["\']([^"\']+\.pdf)', d)]
    return sum(pdf_domains(p, 'grun') for p in pdfs[:2])


def aemcx():
    q = 'https://aemcx.ru/?s=' + urllib.parse.quote('экспортный каталог')
    pages, n = set(), 0
    for pg in range(1, 6):
        _, _, d = get(q + (f'&paged={pg}' if pg > 1 else ''))
        found = set(re.findall(r'https://aemcx\.ru/region_reviews/[\w-]*katalog[\w-]*/', d))
        if not found - pages:
            break
        pages |= found
    for p in sorted(pages):
        _, _, d = get(p)
        for pdf in set(re.findall(r'href=["\'](https://aemcx\.ru/wp-content/uploads/[^"\']+\.pdf)', d)):
            if 'cookie' in pdf.lower() or 'politik' in pdf.lower():
                continue
            try:
                n += pdf_domains(pdf, 'aemcx', p.rstrip('/').rsplit('/', 1)[-1])
            except Exception as e:  # noqa: BLE001
                print('aemcx pdf', pdf, type(e).__name__, flush=True)
    return n


def produkt_by():
    rubs = ['agrokombinaty', 'konservy-detskoe-i-dieticheskoe-pitanie', 'maslo-rastitelnoe-zhir-margarin',
            'muka-i-khleboprodukty', 'napitki-bezalkogolnye', 'ovoschi-frukty-yagody', 'molochnaya-produkciya',
            'selskokhozyaystvennye-predpriyatiya-kfkh', 'bakaleya', 'konditerskie-izdeliya', 'khlebobulochnye-izdeliya']
    n = 0
    for r in rubs:
        for pg in range(0, 30):
            st, _, d = get(f'https://produkt.by/catalog/{r}' + (f'?page={pg}' if pg else ''))
            if not st or st >= 400:
                break
            cards = list(dict.fromkeys(re.findall(r'href=["\'](/catalog/%s/[\w-]+)["\']' % re.escape(r), d)))
            if not cards:
                break
            fresh = 0
            for c in cards:
                card = 'https://produkt.by' + c
                if card in done:
                    continue
                fresh += 1
                _, _, cd = get(card, limit=500_000)
                ext = ext_links(cd, 'produkt.by')
                emit({'source': 'produkt.by', 'rubric': r, 'name': c.rsplit('/', 1)[-1], 'card': card, 'url': '',
                      'domain': ext[0] if ext else ''})
                n += 1
            if not fresh:
                break
    return n


SRC = {'rusprod': rusprod, 'grun': grun, 'aemcx': aemcx, 'produkt_by': produkt_by,
       'expocentr': expocentr, 'productcenter': productcenter}

if __name__ == '__main__':
    if os.path.exists(OUT):
        done |= {json.loads(l)['card'] for l in open(OUT, encoding='utf-8')}
    for name in (sys.argv[1:] or list(SRC)):
        t0 = time.time()
        try:
            n = SRC[name]()
            print(time.strftime('%H:%M:%S'), name, 'ok', n, round(time.time() - t0), 'с', flush=True)
        except Exception as e:  # noqa: BLE001
            print(time.strftime('%H:%M:%S'), name, 'ОШИБКА', type(e).__name__, str(e)[:200], flush=True)
    print('===ИТОГ===', len(done))
