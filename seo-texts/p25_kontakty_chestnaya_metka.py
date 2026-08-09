# -*- coding: utf-8 -*-
"""Честная метка доказательства: какие ссылки в базе РЕАЛЬНО открывают то, ради чего стоят.

Владелец просил проверить глазами 25 случайных ссылок. Проверила, потом ещё пять — и то,
что вышло на выборке, оказалось свойством всей базы, а не случайностью:

    25 ссылок простым запросом:   ДОКАЗЫВАЕТ 12 | открылась без искомого 8 | не открылась 5
    те же 25 браузером:           ДОКАЗЫВАЕТ 12 — БРАУЗЕР НЕ ВЕРНУЛ НИ ОДНОЙ
    ещё 5 новым жребием:          ДОКАЗЫВАЕТ 2 | открылась без искомого 2 | не открылась 1

Гипотезу «это одностраничные приложения, починится браузером» я проверила и она НЕ
подтвердилась. `tender.pro` отрисовывается на 10–23 тысячи знаков, и номера там нет;
`checko.ru` отдаёт заглушку в 2 216 знаков. Номера оттуда были добыты когда-то другим
входом, а ссылка осталась как ссылка на ИСТОЧНИК ДАННЫХ, а не на открываемую страницу.

Разложила по доменам всю базу — и стало видно, что это не хвост, а половина:

    ссылок всего 16 102:  tender.pro 4 124 | monitor-pb 3 318 | checko 2 450 | ЭТП ГПБ 1 318
    строк-контактов, у которых ВСЕ ссылки только checko/tender.pro:  3 196 из 7 140  (45 %)
    строк-машин с тем же свойством:                                    245 из 1 380
    строк-контактов вообще без ссылки:                                 529

Отсюда работа этого скрипта. Он НЕ выбрасывает такие строки — правило владельца «разделять,
а не отсеивать», и номер приёмной, добытый год назад, всё ещё звонит. Он ставит каждой
строке честную метку происхождения доказательства и печатает, сколько остаётся с
доказательством, которое можно открыть СЕГОДНЯ.

ЗАСЛОН ОТ СОБСТВЕННОЙ ПОСПЕШНОСТИ. Заносить домен в «не открывает» по трём случаям нельзя,
а объявлять остальные домены хорошими без проверки — тем более. Поэтому беру случайную
выборку по КАЖДОМУ крупному домену и открываю её с сервера. Метка ставится по замеру, а не
по моему впечатлению, и доля проверенного печатается рядом.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

VHOD = r'C:\sender\_ops\PARK-KONTAKTY-3S.jsonl'
VYHOD = r'C:\sender\_ops\PARK-KONTAKTY-3S-CHESTNO.jsonl'
NA_DOMEN = 6               # сколько ссылок проверять на каждый крупный домен
KRUPNYH = 12
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')


def domen(u):
    """Метку ставлю не домену, а ФОРМЕ АДРЕСА. Домен оказался слишком грубой единицей.

    Пять новых случайных ссылок показали то, чего прошлый замер увидеть не мог:

        https://www.tender.pro/api/tender/856922/view_public   -> ДОКАЗЫВАЕТ, номер найден
        https://www.tender.pro/#/tender/1099290                -> искомого нет никогда

    Это один домен и две разные вещи: первый адрес — ответ API, он отдаёт данные прямо;
    второй — одностраничное приложение, где карточку рисует скрипт. В базе их 2 981 и
    1 074 соответственно, то есть большая часть tender.pro была помечена «не открывается»
    по образцам, случайно попавшим в SPA-форму. Считаю по форме и пересчитываю.
    """
    h = re.sub(r'^https?://([^/]+).*', r'\1', u)
    put = re.sub(r'^https?://[^/]+', '', u)
    if put.startswith('/#') or '/#/' in u:
        return h + ' [приложение, рисует скриптом]'
    if '/api/' in put:
        return h + ' [ответ API]'
    return h + ' [обычная страница]"'.replace('"', '')


stroki = []
for s in io.open(VHOD, encoding='utf-8'):
    try:
        stroki.append(json.loads(s))
    except Exception:  # noqa: BLE001
        pass

po_domenu = collections.defaultdict(list)
for o in stroki:
    for u in (o.get('istochniki') or '').split(' | '):
        if u.startswith('http'):
            po_domenu[domen(u)].append(o)

krupnye = [d for d, v in sorted(po_domenu.items(), key=lambda x: -len(x[1]))[:KRUPNYH]]
random.seed(7788)
proverka = collections.defaultdict(lambda: {'vsego': 0, 'dokazal': 0, 'otkrylas': 0, 'net': 0})
primery = []
for d in krupnye:
    obr = random.sample(po_domenu[d], min(NA_DOMEN, len(po_domenu[d])))
    for o in obr:
        u = next((x for x in (o.get('istochniki') or '').split(' | ')
                  if x.startswith('http') and domen(x) == d), '')
        if not u:
            continue
        z = proverka[d]
        z['vsego'] += 1
        iskat = re.sub(r'\D', '', o.get('nomer') or '')
        pochta = (o.get('pochta') or '').lower()
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
            with net.open(rq, timeout=45) as rs:
                telo = rs.read(400000).decode('utf-8', 'replace')
            text = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
            est = (iskat and iskat in re.sub(r'\D', '', text)) or (pochta and pochta in text.lower())
            if est:
                z['dokazal'] += 1
            else:
                z['otkrylas'] += 1
            if len(primery) < 10:
                primery.append('%-22s %s  %s' % (d, 'ДОКАЗАЛ' if est else 'открылась, нет',
                                                 u[:70]))
        except Exception as e:  # noqa: BLE001
            z['net'] += 1
            if len(primery) < 10:
                primery.append('%-22s НЕ ОТКРЫЛАСЬ %s  %s' % (d, str(e)[:28], u[:60]))

# метка домена по замеру: доказал хоть раз -> «доказательство открывается»
metka_domena = {}
for d, z in proverka.items():
    if z['dokazal'] > 0:
        metka_domena[d] = 'доказательство открывается (проверено %d из %d)' % (z['dokazal'],
                                                                               z['vsego'])
    elif z['otkrylas'] > 0:
        metka_domena[d] = ('страница живая, доказательства на ней нет (проверено %d)'
                           % z['vsego'])
    else:
        metka_domena[d] = 'страница не открывается с сервера (проверено %d)' % z['vsego']

vyhod, svod = [], collections.Counter()
for o in stroki:
    us = [u for u in (o.get('istochniki') or '').split(' | ') if u.startswith('http')]
    if not us:
        m = 'ссылки нет вовсе'
    else:
        metki = {metka_domena.get(domen(u), 'домен не проверялся') for u in us}
        if any(x.startswith('доказательство открывается') for x in metki):
            m = 'есть ссылка, открывающая доказательство'
        elif all(x == 'домен не проверялся' for x in metki):
            m = 'домен не проверялся'
        else:
            m = 'ссылки есть, но доказательство по ним не открывается'
    o['dokazatelstvo_metka'] = m
    o['domeny'] = ' | '.join(sorted({domen(u) for u in us}))
    svod[m] += 1
    vyhod.append(o)

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in vyhod:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'не выкладывала'
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

lich = [o for o in vyhod if o.get('vid_nomera') == 'ЛИЧНЫЙ МОБИЛЬНЫЙ']
lich_ok = [o for o in lich if o['dokazatelstvo_metka'] == 'есть ссылка, открывающая доказательство']
print('\n\n########## ЧТО ОТКРЫЛОСЬ, ПО ОДНОЙ')
for p in primery:
    print('  ' + p)
print('\n########## МЕТКА ДОМЕНА ПО ЗАМЕРУ')
for d in krupnye:
    z = proverka.get(d, {})
    print('  %-24s ссылок в базе %5d | %s' % (d[:24], len(po_domenu[d]),
                                              metka_domena.get(d, '—')))
print('\n########## ЧИСЛА')
print('  строк контактов                       %6d' % len(vyhod))
for k, v in svod.most_common():
    print('     %-52s %6d' % (k[:52], v))
print('  ЛИЧНЫХ МОБИЛЬНЫХ всего                %6d' % len(lich))
print('  из них с ОТКРЫВАЮЩИМСЯ доказательством %5d  (на %d предприятиях)'
      % (len(lich_ok), len({o['inn'] for o in lich_ok})))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'строк': len(vyhod), 'личных': len(lich),
                            'личных с открываемым доказательством': len(lich_ok),
                            'предприятий': len({o['inn'] for o in lich_ok})},
                           ensure_ascii=False))
