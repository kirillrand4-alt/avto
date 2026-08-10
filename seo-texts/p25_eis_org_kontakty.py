# -*- coding: utf-8 -*-
"""У карточки организации ЕИС есть контактное лицо. Смотрю, что там на самом деле.

Прошлый тик показал, где теперь узкое место: имён предприятий хватает (148 добыто из
реестра ЕИС), а личных номеров из них не вышло ни одного. Люди, которых находит поиск по
должности, — главные инженеры и начальники цехов крупных заводов, чьих личных номеров в
открытой выдаче просто нет.

Но у ЕИС есть прямой путь, которым мы не ходили: в карточке организации-заказчика стоит
ОТВЕТСТВЕННОЕ ДОЛЖНОСТНОЕ ЛИЦО с телефоном и почтой. Это не личный мобильный директора, но
это названный человек с должностью, телефоном и ссылкой на страницу ЕИС — то есть строка,
которая в список для звонка годится.

Сначала смотрю разметку живой страницы и печатаю ВСЁ, что там есть про контакты, а потом
уже решаю, что брать. Порядок именно такой: сегодня я четырежды подряд ошиблась, беря
«первое подходящее поле» вместо названного.
"""
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

u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=0266017771'
     '&morphology=on&sortBy=UPDATE_DATE')
h = op.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=60).read().decode(
    'utf-8', 'replace')
ssylki = sorted({x.replace('&amp;', '&') for x in
                 re.findall(r'href="(/epz/organization/[^"]+)"', h)})
print('########## ССЫЛКИ НА КАРТОЧКУ ОРГАНИЗАЦИИ')
for s in ssylki[:8]:
    print('  ' + s[:120])
for s in ssylki[:3]:
    uu = 'https://zakupki.gov.ru' + s
    try:
        hh = op.open(urllib.request.Request(uu, headers={'User-Agent': UA}),
                     timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        print('\n  %s -> не открылась %s' % (s[:60], str(e)[:40]))
        continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', hh))
    print('\n########## %s' % s[:80])
    print('  знаков %d' % len(t))
    for slovo in ('Контактн', 'Ответственн', 'должностн', 'Телефон', 'Электронная почта',
                  'Факс', 'Руководител'):
        i = t.find(slovo)
        if i > 0:
            print('  вокруг «%s»: %s' % (slovo, t[max(0, i - 60):i + 200]))
print('\nИТОГ {"смотрела": "есть ли контактное лицо в карточке организации ЕИС"}')
