# -*- coding: utf-8 -*-
"""ЧТО У СЕРВЕРА С СЕТЬЮ ПОСЛЕ ПЕРЕЗАГРУЗКИ. Диагноз прибора, а не факт о сайтах.

Повод — три пробы подряд с сервера, три разных сайта, одна и та же ошибка:

    example.com          ERR_HTTP_RESPONSE_CODE_FAILURE   (текст 97 байт = страница ошибки)
    roseltorg.ru         ERR_HTTP_RESPONSE_CODE_FAILURE
    zakupki.gov.ru       ERR_HTTP_RESPONSE_CODE_FAILURE

`example.com` не может быть «закрыт» — значит виноват не сайт, а путь до него. Браузер ходит
через `PROXY_URLV3`. Проверяю раздельно:

    1) прямой запрос без прокси            — жива ли сеть сервера вообще
    2) запрос ЧЕРЕЗ тот же прокси          — жив ли прокси
    3) какие прокси-переменные заданы      — печатаю ТОЛЬКО схему, хост и порт

ПАРОЛЬ И ЛОГИН ПРОКСИ НЕ ПЕЧАТАЮТСЯ: из строки вырезается всё до «@». Секреты владельца в
журнал не попадают ни при каких обстоятельствах.

Это важно не ради красоты: если прокси мёртв, любой браузерный канал вернёт ПУСТО, и пустота
будет выглядеть как «на площадке нет закупок» или «у предприятия нет контактов». Соседи прямо
сейчас гонят съёмку и разбор карточек тем же прибором.

Числа в КОНЦЕ.
"""
import json
import os
import re
import ssl
import urllib.request

CELI = ['https://example.com', 'https://zakupki.gov.ru/epz/main/public/home.html',
        'https://www.roseltorg.ru/']
IMENA = ['PROXY_URLV3', 'PROXY_URL', 'HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy']
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def bez_pisem(s):
    """Оставить схему, хост и порт; логин с паролем вырезать."""
    s = str(s or '')
    return re.sub(r'//[^/@]*@', '//<логин скрыт>@', s)[:80]


def proba(u, cherez=None):
    ruch = [urllib.request.HTTPSHandler(context=ctx)]
    ruch.append(urllib.request.ProxyHandler({'http': cherez, 'https': cherez}
                                            if cherez else {}))
    op = urllib.request.build_opener(*ruch)
    try:
        with op.open(urllib.request.Request(u, headers={'User-Agent': 'curl/8.5.0'}),
                     timeout=25) as rs:
            return 'ответ %s, байт %d' % (rs.status, len(rs.read(200000)))
    except Exception as e:  # noqa: BLE001
        return 'отказ: %s' % str(e)[:60]


zadany = {i: bez_pisem(os.environ.get(i)) for i in IMENA if os.environ.get(i)}
proksi = os.environ.get('PROXY_URLV3') or os.environ.get('PROXY_URL') or ''

svod = {}
for u in CELI:
    svod[u] = {'напрямую': proba(u), 'через прокси': proba(u, proksi) if proksi else '—'}

print('\n\n########## ПРОКСИ-ПЕРЕМЕННЫЕ СЕРВЕРА (без логинов и паролей)')
for k, v in zadany.items():
    print('  %-14s %s' % (k, v))
if not zadany:
    print('  ни одна из известных переменных не задана')

print('\n########## ЧТО ОТВЕЧАЕТ СЕТЬ')
for u, v in svod.items():
    print('  %s' % u)
    print('      напрямую      %s' % v['напрямую'])
    print('      через прокси  %s' % v['через прокси'])

pryamo = sum(1 for v in svod.values() if v['напрямую'].startswith('ответ 2'))
cherez = sum(1 for v in svod.values() if str(v['через прокси']).startswith('ответ 2'))
print('\n########## ЧИСЛА')
print('  сайтов проверено          %d' % len(svod))
print('  открылись напрямую        %d' % pryamo)
print('  открылись через прокси    %d' % cherez)
if pryamo and not cherez:
    vyvod = ('сеть сервера жива, МЁРТВ ПРОКСИ — браузерные каналы будут возвращать пустоту, '
             'её нельзя принимать за «данных нет»')
elif not pryamo and not cherez:
    vyvod = 'с сервера не открывается ничего — сеть узла, а не сайты и не прокси'
elif cherez:
    vyvod = 'прокси отвечает; значит браузерная ошибка не в нём — искать в самом браузере'
else:
    vyvod = 'смешанный исход, числа выше'
print('  ВЫВОД: %s' % vyvod)
print('ИТОГ ' + json.dumps({'напрямую': pryamo, 'через прокси': cherez,
                            'переменные': list(zadany)}, ensure_ascii=False))
