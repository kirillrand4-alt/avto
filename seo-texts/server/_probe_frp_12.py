# -*- coding: utf-8 -*-
"""Проба 12: прототип сбора «реестра займов» из пресс-центра ФРП.
Проверяем: работает ли фильтр по датам, пагинация, что достаётся из карточки списка и детальной."""
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
MON = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7,
       'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}


def get(url, timeout=25):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    for _ in range(2):
        try:
            r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
            return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except Exception:                                    # noqa: BLE001
            time.sleep(1)
    return -1, ''


def cards(h):
    out = []
    for blk in re.split(r'<div class="item-news', h)[1:]:
        d = re.search(r'class="date"[^>]*>\s*([^<]+?)\s*<', blk)
        t = re.search(r'class="title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        a = re.search(r'</div>\s*<p>\s*(.*?)\s*</p>', blk, re.S)
        if not t:
            continue
        dt = ''
        if d:
            m = re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', d.group(1))
            if m:
                dt = f'{m.group(3)}-{MON.get(m.group(2), 0):02d}-{int(m.group(1)):02d}'
        out.append({'date': dt, 'link': 'https://frprf.ru' + t.group(1),
                    'title': re.sub(r'<[^>]+>|\s+', ' ', t.group(2)).strip(),
                    'anons': re.sub(r'<[^>]+>|\s+', ' ', a.group(1)).strip() if a else ''})
    return out


rep = []

# A) фильтр по датам + пагинация
base = ('https://frprf.ru/press-tsentr/novosti/?set_filter=y'
        '&arrFilter1_DATE_ACTIVE_FROM_1=01.06.2026&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026')
seen, pages = {}, 0
for p in range(1, 31):
    c, h = get(base + f'&PAGEN_1={p}')
    cc = cards(h)
    pages += 1
    new = [x for x in cc if x['link'] not in seen]
    for x in cc:
        seen[x['link']] = x
    if not new:
        rep.append(f'  стр.{p}: новых 0 -> конец (код {c}, карточек на стр. {len(cc)})')
        break
    rep.append(f'  стр.{p}: {len(cc)} карточек, новых {len(new)}, даты '
               + f'{min(x["date"] for x in cc if x["date"])}..{max(x["date"] for x in cc if x["date"])}')
ds = sorted(x['date'] for x in seen.values() if x['date'])
rep.append(f'ФИЛЬТР 01.06–16.09.2026: страниц {pages}, уникальных новостей {len(seen)}, '
           f'даты {ds[0] if ds else "-"}..{ds[-1] if ds else "-"}')

# сколько из них про займы
LOAN = re.compile(r'займ|заём|заем|ФРП предостав|профинансир|одобрил|выделит|получит.*(млн|млрд)', re.I)
loans = [x for x in seen.values() if LOAN.search(x['title'] + ' ' + x['anons'])]
rep.append(f'  из них похожих на заём: {len(loans)}')

# B) без фильтра — глубина ленты
c, h = get('https://frprf.ru/press-tsentr/novosti/?PAGEN_1=142')
cc = cards(h)
rep.append(f'без фильтра стр.142 -> {c}, карточек {len(cc)}, даты '
           + (f'{cc[0]["date"]}..{cc[-1]["date"]}' if cc else '-'))
c, h = get('https://frprf.ru/press-tsentr/novosti/?PAGEN_1=100')
cc = cards(h)
rep.append(f'без фильтра стр.100 -> {c}, карточек {len(cc)}, даты '
           + (f'{cc[0]["date"]}..{cc[-1]["date"]}' if cc else '-'))

# C) детальная карточка: структура + факты
for it in loans[:3]:
    c, h = get(it['link'])
    m = re.search(r'<h1[^>]*>(.*?)</h1>(.*?)(?:<div class="share|<footer|<div class="also)', h, re.S)
    body = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', m.group(2) if m else '')
    body = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body)).strip()
    rep.append(f'--- {it["date"]} {it["title"][:90]}')
    rep.append('    URL ' + it['link'][:110])
    rep.append('    тело[:900]: ' + body[:900])

print('\n'.join(rep[-110:]))
sys.stdout.flush()
