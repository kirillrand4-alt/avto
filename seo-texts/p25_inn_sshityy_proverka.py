# -*- coding: utf-8 -*-
"""Сколько моих ИНН, сшитых ПО НАЗВАНИЮ, оказались чужими. Класс назвала 1-я сессия.

Она померила у себя: 35 снимков из 2 569 по 223-ФЗ (1,4 %) показали на странице ИНН,
отличный от того, что стоит в факте, — потому что ИНН сшивался по НАЗВАНИЮ, а однофамильных
юрлиц много. Среди источников помеченных назвала и мои потоки. Проверяю у себя.

Population под вопросом видна сразу: в срезе `PARK-EIS-TIK12-PODTV-3S.jsonl` из 2 029 строк
**809 получили ИНН с карточки организации** (это надёжно), **265 — «сшит по названию с
enrich.db»** (это и есть риск), 955 без ИНН вовсе.

Мерка простая и честная: беру строки со сшитым ИНН, открываю ИХ ЖЕ карточку извещения с
сервера, вынимаю ИНН заказчика со страницы и сравниваю. Три исхода:

    совпал            — сшивка верна
    НЕ СОВПАЛ         — в факте чужой ИНН, строка помечается
    ИНН на странице нет — по 44-ФЗ его часто не печатают, это не улика

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: к выборке подмешивается строка с намеренно подменённым ИНН
(первые две цифры переставлены). Если мерка не заметит подмену — она не умеет говорить «нет».

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

OPS = r'C:\sender\_ops'
VHODY = ['PARK-EIS-TIK12-PODTV-3S.jsonl', 'PARK-EIS-TIK13-PODTV-3S.jsonl',
         'PARK-EIS-TIK10-PODTV-3S.jsonl']
SKOLKO = int(os.environ.get('P25_SKOLKO', '40'))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
INN_NA_STR = re.compile(r'ИНН[^0-9]{0,12}(\d{10}|\d{12})')


def tekst(u):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
        return re.sub(r'\s+', ' ', TEG.sub(' ', net.open(rq, timeout=40)
                                           .read(400000).decode('utf-8', 'replace')))
    except Exception:  # noqa: BLE001
        return ''


celi = []
for f in VHODY:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if 'сшит по названию' not in str(o.get('inn_otkuda') or ''):
            continue
        # НОЛЬ ЦЕЛЕЙ БЫЛ ДИАГНОЗОМ ПРИБОРА. Я искала ссылку вида `common-info`, а у строк со
        # сшитым ИНН лежат другие: поиск по ПОЛНОМУ реестровому номеру (постоянная ссылка на
        # одно извещение — моё же правило) и карточка организации. Беру первую подходящую.
        # ВТОРОЙ ПРОМАХ ПРИБОРА: ссылка `extendedsearch/results.html?searchString=<номер>`
        # открывает СПИСОК результатов, а ЕИС не печатает ИНН в списке — все 41 проба дали
        # «ИНН на странице не напечатан». Карточку надо строить из реестрового номера:
        # 44-ФЗ — форма ea44, 223-ФЗ (номер начинается с 3) — своя форма. Эту форму я уже
        # проверяла отдельным замером, беру её.
        us = [x for x in str(o.get('istochniki') or '').split(' | ') if x.startswith('http')]
        u = next((x for x in us if 'common-info' in x), '')
        if not u:
            m = next((re.search(r'searchString=(\d{11,25})(?:&|$)', x) for x in us
                      if re.search(r'searchString=\d{11,25}(?:&|$)', x)), None)
            if m:
                nom = m.group(1)
                u = ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
                     'common-info.html?regNumber=%s' % nom if nom.startswith('3')
                     else 'https://zakupki.gov.ru/epz/order/notice/ea44/view/'
                          'common-info.html?regNumber=%s' % nom)
        if u and str(o.get('inn') or '').isdigit():
            celi.append((o, u))

random.seed(int(os.environ.get('P25_ZHREBIY', '4242')))
random.shuffle(celi)
obr = celi[:SKOLKO]
# отрицательный контроль: та же строка, но с подменённым ИНН
kontrol = None
if obr:
    o0, u0 = obr[0]
    lozh = dict(o0)
    c = str(o0['inn'])
    lozh['inn'] = c[1] + c[0] + c[2:]
    kontrol = (lozh, u0)

sch = collections.Counter()
chuzhie = []
for o, u in obr + ([kontrol] if kontrol else []):
    t = tekst(u)
    if not t:
        sch['страница не открылась — не улика'] += 1
        continue
    na_str = set(INN_NA_STR.findall(t))
    etot = kontrol is not None and o is kontrol[0]
    if not na_str:
        sch['ИНН на странице не напечатан (44-ФЗ) — не улика'] += 1
        continue
    if str(o['inn']) in na_str:
        sch['КОНТРОЛЬ пропустил подмену' if etot else 'совпал: сшивка верна'] += 1
    else:
        sch['КОНТРОЛЬ поймал подмену' if etot else 'НЕ СОВПАЛ: в факте чужой ИНН'] += 1
        if not etot and len(chuzhie) < 8:
            chuzhie.append((o['inn'], ', '.join(sorted(na_str))[:40],
                            (o.get('zakazchik') or '')[:44], u[:60]))

print('\n\n########## ГДЕ ИНН РАЗОШЁЛСЯ')
for x in chuzhie:
    print('  в факте %-12s на странице %-40s %s' % (x[0], x[1], x[2]))
    print('        %s' % x[3])
print('\n########## ЧИСЛА')
print('  строк со сшитым по названию ИНН и карточкой: %d' % len(celi))
print('  проверено за заход                           %d' % len(obr))
for k, v in sch.most_common():
    print('     %-52s %5d' % (k[:52], v))
proverено = sch['совпал: сшивка верна'] + sch['НЕ СОВПАЛ: в факте чужой ИНН']
print('  доля чужих среди тех, где ИНН на странице есть: %s'
      % ('%.0f%%' % (100.0 * sch['НЕ СОВПАЛ: в факте чужой ИНН'] / proverено)
         if proverено else '—'))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: %s'
      % ('подмену поймал' if sch['КОНТРОЛЬ поймал подмену'] else
         'ПОДМЕНУ ПРОПУСТИЛ — мерке верить нельзя'))
print('ИТОГ ' + json.dumps({'целей': len(celi), 'проверено': len(obr),
                            'чужих': sch['НЕ СОВПАЛ: в факте чужой ИНН'],
                            'контроль': bool(sch['КОНТРОЛЬ поймал подмену'])},
                           ensure_ascii=False))
