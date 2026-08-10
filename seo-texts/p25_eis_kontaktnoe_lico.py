# -*- coding: utf-8 -*-
"""Контактное лицо из карточек закупок ЕИС — канал, который у соседа дал лучший выход.

Замер трёх обходов, из которого это следует:

    мои найденные поиском люди   558 обойдено -> телефон у  62  (11 %)
    люди 1-й сессии (аттестация) 660         -> телефон у  48  ( 7 %)
    люди 2-й сессии (карточки закупок) 540   -> телефон у 119  (22 %)

Люди 2-й сессии находятся вдвое лучше не потому, что она лучше искала, а потому что взяты
из карточек закупок, где контактное лицо стоит рядом с предметом и с телефоном. Значит идти
надо туда напрямую, а не искать этих же людей потом в выдаче.

У меня 544 карточки ЕИС, собранные по словам номенклатуры, и путь к самой карточке уже
проверен: поиск по номеру -> ссылка из блока номера -> карточка. Беру оттуда блок
«Контактная информация»: ФИО, телефон, почту.

ЗАСЛОН НА РЕЗУЛЬТАТ, а не на источник — сегодняшний урок, стоивший четырёх заходов:
   • ФИО обязано быть похоже на ФИО (три слова с отчеством либо фамилия с инициалами);
   • телефон обязан быть телефонного вида, а не любым числом;
   • если в блоке нет ни ФИО, ни телефона — строка не пишется, причина считается.

Числа в КОНЦЕ.
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
VYHOD = r'C:\sender\_ops\PARK-EIS-KONTAKTNOE-LICO-3S.jsonl'
SKOLKO = 180
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
KARTA = re.compile(r'registry-entry__header-mid__number[^>]*>\s*<a[^>]*href="([^"]+)"', re.S)
FIO = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+'
                 r'[А-ЯЁ][а-яё\-]{2,}(?:ович|евич|ич|овна|евна|ична))\b')
FIO2 = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)')
TELEFON = re.compile(r'(?:\+?7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


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

potok, prichiny = [], collections.Counter()
for o in zayavki:
    u1 = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString='
          + o['nomer'])
    try:
        h = tyanut(u1)
    except Exception:  # noqa: BLE001
        prichiny['поиск по номеру не открылся'] += 1
        continue
    m = KARTA.search(h)
    if not m:
        prichiny['ссылки на карточку в выдаче нет'] += 1
        continue
    a = m.group(1).replace('&amp;', '&').strip()
    u2 = a if a.startswith('http') else 'https://zakupki.gov.ru' + a
    try:
        hk = tyanut(u2)
    except Exception:  # noqa: BLE001
        prichiny['карточка не открылась'] += 1
        continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', hk))
    i = t.find('Контактная информация')
    okno = t[i:i + 1600] if i > 0 else t
    if i <= 0:
        prichiny['блока «Контактная информация» на карточке нет'] += 1
    fio = (FIO.search(okno) or FIO2.search(okno))
    tel = TELEFON.search(okno)
    poch = POCHTA.search(okno)
    if not fio and not tel:
        prichiny['ни ФИО, ни телефона в блоке'] += 1
        continue
    potok.append({'inn': o['inn'], 'zakazchik': o.get('zakazchik', '')[:120],
                  'nomer_zakupki': o['nomer'],
                  'imya': fio.group(1) if fio else '',
                  'telefon': tel.group(0) if tel else '',
                  'pochta': poch.group(0) if poch else '',
                  'predmet': o.get('predmet', '')[:160],
                  'istochniki': u2 + ' | ' + u1, 'istochnikov': 2,
                  'kto': '3-я сессия, контактное лицо из карточки ЕИС'})
    prichiny['взято'] += 1
    time.sleep(0.3)

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = o2.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

s_imenem = [o for o in potok if o['imya']]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in potok[:10]:
    print('  %-12s %-28s %-18s %s' % (o['inn'], (o['imya'] or '—')[:28],
                                      o['telefon'][:18], o['pochta'][:32]))
print('\n########## ЧИСЛА')
print('  карточек опрошено        %5d' % len(zayavki))
print('  строк с контактом        %5d  (разных ИНН %d)'
      % (len(potok), len({o['inn'] for o in potok})))
print('  из них с ФИО             %5d' % len(s_imenem))
print('  с телефоном              %5d' % sum(1 for o in potok if o['telefon']))
print('  с почтой                 %5d' % sum(1 for o in potok if o['pochta']))
print('  --- по причинам')
for k, v in prichiny.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'опрошено': len(zayavki), 'с контактом': len(potok),
                            'с ФИО': len(s_imenem)}, ensure_ascii=False))
