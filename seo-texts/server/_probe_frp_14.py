# -*- coding: utf-8 -*-
"""Проба 14: рабочий прототип «реестра займов ФРП» из пресс-центра.
Считаем покрытие: сколько всего новостей в ленте, сколько из них про займы за год."""
import re
import ssl
import sys
import time
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
    for _ in range(2):
        try:
            r = _OP.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout)
            return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except Exception:                                    # noqa: BLE001
            time.sleep(1)
    return -1, ''


def cards(h):
    out = []
    for blk in re.split(r'class="item-news', h)[1:]:
        t = re.search(r'class="title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not t:
            continue
        d = re.search(r'class="date"[^>]*>\s*([^<]+?)\s*<', blk)
        dt = ''
        if d:
            m = re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', d.group(1))
            if m:
                dt = '%s-%02d-%02d' % (m.group(3), MON.get(m.group(2), 0), int(m.group(1)))
        a = re.search(r'</div>\s*<p>\s*(.*?)\s*</p>', blk, re.S)
        out.append({'date': dt, 'link': 'https://frprf.ru' + t.group(1),
                    'title': re.sub(r'<[^>]+>|\s+', ' ', t.group(2)).strip(),
                    'anons': re.sub(r'<[^>]+>|\s+', ' ', a.group(1)).strip() if a else ''})
    return out


LOAN = re.compile(r'за[её]м|займ|ФРП предостав|профинансир|одобрил|выделит|'
                  r'льготн\w+ финансиров', re.I)
rep = []

# 1) глубина ленты
for p in (142, 143, 145, 150):
    c, h = get(f'https://frprf.ru/press-tsentr/novosti/?PAGEN_1={p}')
    cc = cards(h)
    rep.append(f'  стр.{p}: код {c}, карточек {len(cc)}, даты '
               + (f'{cc[-1]["date"]}..{cc[0]["date"]}' if cc else '-'))

# 2) год через фильтр дат
base = ('https://frprf.ru/press-tsentr/novosti/?set_filter=y'
        '&arrFilter1_DATE_ACTIVE_FROM_1=16.09.2025&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026')
seen = {}
t0 = time.time()
for p in range(1, 61):
    c, h = get(base + f'&PAGEN_1={p}')
    cc = cards(h)
    new = [x for x in cc if x['link'] not in seen]
    for x in cc:
        seen[x['link']] = x
    if not new:
        rep.append(f'  конец на стр.{p} (карточек {len(cc)}, новых 0)')
        break
ds = sorted(x['date'] for x in seen.values() if x['date'])
loans = [x for x in seen.values() if LOAN.search(x['title'] + ' ' + x['anons'])]
rep.append(f'ГОД 16.09.2025–16.09.2026: новостей {len(seen)}, даты {ds[0] if ds else "-"}..'
           f'{ds[-1] if ds else "-"}, про займы {len(loans)}, время {round(time.time() - t0)}с')

# 3) 90 дней
base90 = ('https://frprf.ru/press-tsentr/novosti/?set_filter=y'
          '&arrFilter1_DATE_ACTIVE_FROM_1=18.06.2026&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026')
s90 = {}
for p in range(1, 31):
    c, h = get(base90 + f'&PAGEN_1={p}')
    cc = cards(h)
    new = [x for x in cc if x['link'] not in s90]
    for x in cc:
        s90[x['link']] = x
    if not new:
        break
l90 = [x for x in s90.values() if LOAN.search(x['title'] + ' ' + x['anons'])]
rep.append(f'90 ДНЕЙ: новостей {len(s90)}, про займы {len(l90)}')

# 4) примеры
rep.append('--- примеры «займовых» новостей (дата | сумма из заголовка | заголовок):')
for x in sorted(l90, key=lambda z: z['date'], reverse=True)[:14]:
    s = re.search(r'(\d[\d ,\.]*)\s*(млн|млрд)', x['title'] + ' ' + x['anons'])
    rep.append(f'   {x["date"]} | {(s.group(0) if s else "-"):>12} | {x["title"][:95]}')

print('\n'.join(rep[-90:]))
sys.stdout.flush()
