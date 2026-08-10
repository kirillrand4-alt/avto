# -*- coding: utf-8 -*-
"""Портал Москвы: ссылка открывается, а машины в теле нет. Ищу форму, где содержимое ЕСТЬ.

Проверка пяти случайных ссылок дала две строки `zakupki.mos.ru`, у которых страница
открылась, а обозначения машины на ней нет. Это ровно тот же случай, что был у
`tender.pro/#/tender/N`: карточку рисует скрипт, в теле ответа лежит только каркас.
Тогда лечение нашлось в форме `/api/tender/N/view_public` — значит и здесь надо спросить
у площадки её собственный API, а не объявлять факт недоказанным.

Из песочницы портал отвечает `Connection reset by peer`, поэтому меряю С СЕРВЕРА.

Заслон: форма считается рабочей, только если в теле ответа стоит СЛОВО МАШИНЫ. Ответ 200
с каркасом — это не доказательство, а тот же каркас.

Числа в КОНЦЕ.
"""
import json
import re
import ssl
import urllib.request

PRIMERY = [('аукцион', '9485656', [
    'https://zakupki.mos.ru/auction/%s',
    'https://old.zakupki.mos.ru/api/Cssp/Auction/GetAuctionItem?auctionId=%s',
    'https://zakupki.mos.ru/newapi/api/Auction/Get?auctionId=%s',
    'https://zakupki.mos.ru/api/Cssp/Auction/GetAuctionItem?auctionId=%s']),
    ('потребность', '4640755', [
        'https://zakupki.mos.ru/need/%s',
        'https://old.zakupki.mos.ru/api/Cssp/Need/GetNeedItem?needId=%s',
        'https://zakupki.mos.ru/newapi/api/Need/Get?needId=%s',
        'https://zakupki.mos.ru/api/Cssp/Need/GetNeedItem?needId=%s'])]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
MASHINA = re.compile(r'компрессор|воздуходув|нагнетател|азот|кислород|осушител', re.I)

itogi = []
for vid, nomer, formy in PRIMERY:
    for f in formy:
        u = f % nomer
        try:
            with net.open(urllib.request.Request(
                    u, headers={'User-Agent': UA, 'Accept': 'application/json,text/html,*/*',
                                'Accept-Language': 'ru'}), timeout=45) as rs:
                telo = rs.read(400000).decode('utf-8', 'replace')
                kod = str(rs.status)
        except Exception as e:  # noqa: BLE001
            itogi.append((vid, u, '—', 0, False, str(e)[:44]))
            continue
        itogi.append((vid, u, kod, len(telo), bool(MASHINA.search(telo)), ''))

print('\n\n########## ЧТО ОТВЕТИЛА КАЖДАЯ ФОРМА')
for vid, u, kod, dlina, est, err in itogi:
    print('  %-12s код %-4s тело %7d знаков, машина в теле: %-3s %s'
          % (vid, kod, dlina, 'ДА' if est else 'нет', err))
    print('        %s' % u[:100])
rab = [x for x in itogi if x[4]]
print('\n########## ЧИСЛА')
print('  форм проверено            %2d' % len(itogi))
print('  форм, где машина В ТЕЛЕ   %2d' % len(rab))
for x in rab:
    print('     РАБОЧАЯ: %s' % x[1][:96])
print('ИТОГ ' + json.dumps({'форм': len(itogi), 'рабочих': len(rab),
                            'адреса': [x[1] for x in rab]}, ensure_ascii=False))
