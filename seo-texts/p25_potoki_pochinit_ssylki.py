# -*- coding: utf-8 -*-
"""Починка адресов В САМИХ ПОТОКАХ парка. Витрину я вылечила, источник — нет.

Замер доли доказанных ПО ДОМЕНАМ (жребий 555, по шесть ссылок на домен) показал 31 %
вместо тех «5 из 5», которые давали два случайных жребия подряд. И разложение по доменам
назвало причину поимённо:

    etpgpb.ru        4 456 строк, 6 проб из 6 — 'ascii' codec can't encode
    zakupki.mos.ru      57 строк, 6 из 6 — каркас без машины
    zakupki.gov.ru   4 865 строк, доказала 1 из 6 — первой стоит ссылка «как искали»
    monitor-pb.ru      846 строк, 6 из 6 ДОКАЗЫВАЕТ
    roseltorg.ru        15 строк, 6 из 6 ДОКАЗЫВАЕТ

Первые две поломки я чинила час назад — но ТОЛЬКО в сборщиках списков. В потоках адреса
остались сырыми, и всякий, кто возьмёт поток (а 1-я сессия его уже влила), получит те же
битые ссылки. **Починка, не доехавшая до источника, — это починка витрины.**

Здесь три правки, все три уже проверены отдельными замерами:

  1. кириллица в адресе → процентное кодирование, IDN-хост → punycode
     (`etpgpb.ru/procedures/?search=ГП830249` падал на 'ascii' codec);
  2. `zakupki.mos.ru/auction|need/N` → `newapi/api/Auction|Need/Get`
     (обычная страница отдаёт каркас 7 992 знака без машины, newapi — с машиной);
  3. `tender.pro/#/tender/N` → `/api/tender/N/view_public`.

И четвёртая, порядковая: ссылка-ДОКАЗАТЕЛЬСТВО ставится первой, «как искали» — после неё.
Проверяльщик берёт первую ссылку, и из-за порядка zakupki.gov.ru показывал 1 из 6, хотя
карточка в строке была.

Ничего не удаляется: все ссылки остаются, меняется форма и порядок.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.parse as _up
import urllib.request

OPS = r'C:\sender\_ops'
FAJLY = ['park_ingest_3d.jsonl', 'park_ingest_3.jsonl', 'park_ingest_3b.jsonl',
         'park_ingest_3c.jsonl']
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
POISK_PO_SLOVU = re.compile(r'(?:extendedsearch|/search)/results\.html\?(?!.*searchString=\d{11,25})')


def pochinit(u):
    if not u or not u.startswith('http'):
        return u
    m = re.match(r'^https?://(?:www\.)?tender\.pro/#/tender/(\d+)', u)
    if m:
        u = 'https://www.tender.pro/api/tender/%s/view_public' % m.group(1)
    m = re.match(r'^https?://(?:www\.)?zakupki\.mos\.ru/auction/(\d+)', u)
    if m:
        u = 'https://zakupki.mos.ru/newapi/api/Auction/Get?auctionId=%s' % m.group(1)
    m = re.match(r'^https?://(?:www\.)?zakupki\.mos\.ru/need/(\d+)', u)
    if m:
        u = 'https://zakupki.mos.ru/newapi/api/Need/Get?needId=%s' % m.group(1)
    try:
        p = _up.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        u = _up.urlunsplit((p.scheme, host,
                            _up.quote(p.path, safe="/%:@&=+$,~!*'()"),
                            _up.quote(p.query, safe="/%:@&=+$,?~!*'()"), ''))
    except Exception:  # noqa: BLE001
        pass
    return u


svod = collections.Counter()
for f in FAJLY:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        svod['НЕТ ФАЙЛА: %s' % f] += 1
        continue
    stroki, izmeneno = [], 0
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        novye = []
        for u in us:
            n = pochinit(u)
            if n != u:
                izmeneno += 1
                if re.search(r'[^\x00-\x7F]', u):
                    svod['кириллица в адресе закодирована'] += 1
                elif 'mos.ru' in u:
                    svod['портал Москвы переведён на рабочую форму'] += 1
                else:
                    svod['tender.pro переведён на форму API'] += 1
            novye.append(n)
        # ПОРЯДОК: доказательство первым, «как искали» после
        dok = [u for u in novye if not POISK_PO_SLOVU.search(u)]
        kak = [u for u in novye if POISK_PO_SLOVU.search(u)]
        if kak and dok and novye[0] in kak:
            svod['строк, где «как искали» стояло первым — переставлено'] += 1
        o['istochniki'] = ' | '.join(dok + kak)
        o['istochnikov'] = len(dok + kak)
        o['ssylok_dokazatelstv'] = len(dok)
        stroki.append(o)
    with io.open(put, 'w', encoding='utf-8') as g:
        for o in stroki:
            g.write(json.dumps(o, ensure_ascii=False) + '\n')
    svod['%s: строк' % f] = len(stroki)
    svod['%s: адресов исправлено' % f] = izmeneno
    try:
        rq = urllib.request.Request('%s/%s' % (drop, f),
                                    data=io.open(put, 'rb').read(), method='PUT', headers=tok)
        op.open(rq, timeout=300).read()
        svod['%s: выложен' % f] = 1
    except Exception as e:  # noqa: BLE001
        print('НЕ ВЫЛОЖЕН %s: %s' % (f, str(e)[:60]))

print('\n\n########## ЧИСЛА')
for k, v in svod.most_common():
    print('  %-52s %6d' % (k[:52], v))
print('ИТОГ ' + json.dumps(dict(svod), ensure_ascii=False))
