# -*- coding: utf-8 -*-
"""Где у карточки ЕИС лежит ОКПД2. Общая вкладка его почти не печатает: 4 из 211.

Адрес карточки я наконец собираю верно — ошибок сети ноль, карточка найдена у всех 211.
Но код нашёлся только у четырёх, и это не «ЕИС не публикует», а «код лежит не на общей
вкладке». Смотрю ВКЛАДКИ одной живой карточки и ищу, на какой из них слово ОКПД вообще
встречается. Без этого следующий заход снова будет гаданием.

Числа в КОНЦЕ.
"""
import io
import json
import re
import ssl
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
VHOD = r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl'
KARTA = re.compile(r'registry-entry__header-mid__number[^>]*>\s*<a[^>]*href="([^"]+)"', re.S)


def tyanut(u):
    return op.open(urllib.request.Request(u, headers={'User-Agent': UA}),
                   timeout=60).read().decode('utf-8', 'replace')


nomera = []
for s in io.open(VHOD, encoding='utf-8'):
    o = json.loads(s)
    if o.get('slovo_podtverzhdeno_tekstom'):
        nomera.append(o['nomer'])
    if len(nomera) >= 3:
        break

itog = {}
for nom in nomera:
    h = tyanut('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=' + nom)
    m = KARTA.search(h)
    if not m:
        continue
    a = m.group(1).replace('&amp;', '&').strip()
    u0 = a if a.startswith('http') else 'https://zakupki.gov.ru' + a
    hk = tyanut(u0)
    vkladki = sorted({x.replace('&amp;', '&') for x in
                      re.findall(r'href="(/epz/order/notice/[^"]+)"', hk)})
    print('\n########## ИЗВЕЩЕНИЕ %s' % nom)
    print('  карточка: %s' % u0[:120])
    print('  вкладок найдено: %d' % len(vkladki))
    for v in vkladki[:10]:
        uv = 'https://zakupki.gov.ru' + v
        try:
            t = re.sub(r'\s+', ' ', TEG.sub(' ', tyanut(uv)))
            est = 'ОКПД' in t.upper()
            kody = re.findall(r'ОКПД\s*2?[^0-9]{0,30}(\d{2}(?:\.\d{1,2}){1,4})', t, re.I)
            print('     %-58s ОКПД %-5s кодов %d' % (v[:58], est, len(set(kody))))
            if kody:
                itog.setdefault(nom, []).extend(sorted(set(kody))[:4])
        except Exception as e:  # noqa: BLE001
            print('     %-58s не открылась %s' % (v[:58], str(e)[:34]))
print('\n########## ЧИСЛА')
print('  извещений просмотрено %d, из них код нашёлся у %d' % (len(nomera), len(itog)))
for k, v in itog.items():
    print('     %s -> %s' % (k, ' | '.join(sorted(set(v))[:6])))
print('ИТОГ ' + json.dumps({'извещений': len(nomera), 'с кодом': len(itog)}, ensure_ascii=False))
