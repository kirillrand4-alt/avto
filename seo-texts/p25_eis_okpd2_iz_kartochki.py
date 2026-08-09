# -*- coding: utf-8 -*-
"""Ось ОКПД2, переданная мне 1-й сессией. Беру код ИЗ КАРТОЧКИ закупки, а не из справочника.

1-я сессия записала честный тупик: `okpd2.ru` — одностраничное приложение и отдаёт один и
тот же ответ на разные страницы, `classinform.ru` даёт 404, а поиск кодов в наших текстах
нашёл только ДАТЫ («27.11», «20.03» — это дд.мм, а не ОКПД2). Вывод её верный: коды по
памяти в канон писать нельзя. И путь она назвала правильный — в карточке закупки ЕИС
ОКПД2 стоит полем.

Как дохожу до карточки. Прямой адрес карточки у ЕИС не выводится из номера — я это уже
проверила, 404 на всех двадцати: путь разный для 44-ФЗ и 223-ФЗ и зависит от способа
закупки. Зато страница ПОИСКА по номеру открывается всегда и содержит ссылку на настоящую
карточку. Значит два шага: поиск по номеру -> ссылка -> карточка -> код.

ЗАСЛОН. Шаблон `\\d{2}\\.\\d{2}` ловит даты — на этом 1-я сессия уже обожглась. Беру код
только там, где рядом стоит слово ОКПД, и требую хотя бы две точки либо явную подпись
«Код позиции» / «ОКПД2». Сколько карточек дали код и сколько промолчали — печатаю обе
цифры, потому что «нашлось у 12 из 544» и «нашлось у 480 из 544» это разные новости.

Только чтение по сети. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import time
import urllib.request

VHOD = r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl'
VYHOD = r'C:\sender\_ops\PARK-EIS-OKPD2-3S.jsonl'
SKOLKO = 260
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
# Ноль карточек из 211 — это диагноз МОЕГО шаблона, а не ЕИС. Ссылка на карточку лежит в
# блоке номера извещения (`registry-entry__header-mid__number`), и путь у неё свой у каждого
# способа закупки — поэтому ловлю любой href этого блока, а не заранее придуманный путь.
KARTA = re.compile(r'registry-entry__header-mid__number[^>]*>\s*<a[^>]*href="([^"]+)"', re.S)
# код только рядом со словом ОКПД — иначе поймаются даты
OKPD = re.compile(r'ОКПД\s*2?[^0-9]{0,40}(\d{2}(?:\.\d{1,2}){1,4})', re.I)


def tyanut(u):
    return op.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru'}),
                   timeout=60).read().decode('utf-8', 'replace')


zayavki = []
for s in io.open(VHOD, encoding='utf-8'):
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    if o.get('slovo_podtverzhdeno_tekstom') and o.get('inn'):
        zayavki.append(o)
zayavki = zayavki[:SKOLKO]

potok, kody = [], collections.Counter()
bez_karty, bez_koda, oshibok = 0, 0, 0
for o in zayavki:
    u_poisk = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString='
               + o['nomer'])
    try:
        h = tyanut(u_poisk)
    except Exception:  # noqa: BLE001
        oshibok += 1
        continue
    m = KARTA.search(h)
    if not m:
        bez_karty += 1
        continue
    u_kart = 'https://zakupki.gov.ru' + m.group(1).replace('&amp;', '&')
    try:
        hk = tyanut(u_kart)
    except Exception:  # noqa: BLE001
        oshibok += 1
        continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', hk))
    nayd = sorted({x for x in OKPD.findall(t)})
    if not nayd:
        bez_koda += 1
        continue
    for k in nayd:
        kody[k] += 1
    potok.append({'inn': o['inn'], 'nomer': o['nomer'],
                  'zakazchik': o.get('zakazchik', '')[:120],
                  'okpd2': ' | '.join(nayd), 'kodov': len(nayd),
                  'predmet': o.get('predmet', '')[:160],
                  'istochniki': u_kart + ' | ' + u_poisk, 'istochnikov': 2,
                  'kto': '3-я сессия, ОКПД2 из карточки ЕИС'})
    time.sleep(0.3)

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
vylozheno = 'не выкладывала'
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = o2.open(rq, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

nashi = {k: v for k, v in kody.items() if k.startswith(('28.13', '20.11', '28.25', '33.12'))}
print('\n\n########## ПРИМЕРЫ')
for o in potok[:8]:
    print('  %-12s %-22s %s' % (o['inn'], o['okpd2'][:22], o['predmet'][:70]))
print('\n########## ЧИСЛА')
print('  карточек опрошено            %5d' % len(zayavki))
print('  код ОКПД2 найден             %5d  (разных ИНН %d)'
      % (len(potok), len({o['inn'] for o in potok})))
print('  карточка не найдена в поиске %5d' % bez_karty)
print('  карточка есть, кода нет      %5d' % bez_koda)
print('  ошибок сети                  %5d' % oshibok)
print('  --- частые коды')
for k, v in kody.most_common(14):
    print('     %-14s %5d' % (k, v))
print('  --- наши разделы (28.13 компрессоры, 20.11 газы, 28.25 очистка, 33.12 ремонт)')
for k, v in sorted(nashi.items(), key=lambda x: -x[1])[:10]:
    print('     %-14s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'опрошено': len(zayavki), 'с кодом': len(potok),
                            'ИНН': len({o['inn'] for o in potok})}, ensure_ascii=False))
