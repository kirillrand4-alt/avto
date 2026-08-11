# -*- coding: utf-8 -*-
"""1-я сессия (запись 141.4) нашла в МОИХ данных ложное доказательство номера: карточка
`prodoctorov.ru` — Казанцева Галина Валерьевна, неонатолог-педиатр из Челябинска, — стояла
доказательством номера начальника цеха водоканала. Полная тёзка. Их признак спрашивал два
вопроса (есть ли номер, стоит ли рядом фамилия) и не спрашивал третьего: ОТНОСИТСЯ ЛИ
СТРАНИЦА К НАШЕМУ ПРЕДПРИЯТИЮ.

Ровно то же третье условие я час назад добавила для ссылок-МАШИН и к КОНТАКТАМ не применила.
Меряю размер беды у себя: сколько строк базы (и сколько личных мобильных) держатся на
страницах-агрегаторах, где связь человека с предприятием доказать нечем.

Ноль по любому хосту будет означать, что таких ссылок нет, а не что я их не искала: список
хостов печатается целиком, включая нулевые.
"""
import collections, csv, io, json, os, re, urllib.parse
OPS = r'C:\sender\_ops'
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
# Хосты, где карточку заводит НЕ предприятие: тёзка неотличима от нашего человека.
AGREGATORY = ['prodoctorov.ru', 'vk.com', 'ok.ru', 'facebook.com', 'careerist.ru', 'hh.ru',
              'avito.ru', '2gis.ru', 'zoon.ru', 'yell.ru', 'orgpage.ru', 'rusprofile.ru',
              'list-org.com', 'checko.ru', 'sbis.ru', 'zachestnyibiznes.ru', 'audit-it.ru',
              'telefonnyj-spravochnik', 'spravkaru', 'nomer.io', 'kodtelefona']
# Хосты, где карточку заводит сам заказчик или само предприятие — связь есть по устройству.
SVOI = ['zakupki.gov.ru', 'etpgpb.ru', 'roseltorg.ru', 'tektorg.ru', 'rts-tender.ru',
        'tender.pro', 'zakupki.mos.ru', 'fabrikant.ru', 'b2b-center.ru', 'monitor-pb.ru']
rows = list(csv.DictReader(io.open(BAZA, encoding='utf-8-sig'), delimiter=';'))
sch = collections.Counter()
po_hostam = collections.Counter()
lich_agr = []
for r in rows:
    lichnyy = (r.get('vid_nomera') or '').strip().upper().startswith('ЛИЧНЫЙ')
    us = [u for u in str(r.get('istochniki') or '').split(' | ') if u.startswith('http')]
    if not us:
        sch['строк без ссылок'] += 1
        continue
    hosty = set()
    for u in us:
        try:
            hosty.add(urllib.parse.urlsplit(u).netloc.replace('www.', '').lower())
        except Exception:  # noqa: BLE001
            pass
    agr = {h for h in hosty if any(a in h for a in AGREGATORY)}
    svoi = {h for h in hosty if any(s in h for s in SVOI)}
    if lichnyy:
        sch['ЛИЧНЫХ МОБИЛЬНЫХ всего'] += 1
        if agr and not svoi:
            sch['   личный: ВСЕ ссылки — агрегаторы (связь с предприятием не доказана)'] += 1
            lich_agr.append((r.get('inn'), (r.get('chelovek') or '')[:28], r.get('nomer'),
                             sorted(agr)[0], us[0][:70]))
        elif agr and svoi:
            sch['   личный: есть и агрегатор, и своя площадка'] += 1
        elif svoi:
            sch['   личный: только свои площадки / сайт предприятия'] += 1
        else:
            sch['   личный: прочие хосты (ни агрегатор, ни площадка)'] += 1
    for h in hosty:
        po_hostam[h] += 1
print('########## ЧИСЛА (живой файл PARK-BAZA-EDINAYA-3S.csv, строк %d)' % len(rows))
for k, v in sch.most_common():
    print('  %-62s %5d' % (k[:62], v))
print('  --- ХОСТЫ-АГРЕГАТОРЫ В БАЗЕ, все из списка, включая нулевые')
for a in AGREGATORY:
    n = sum(v for h, v in po_hostam.items() if a in h)
    print('     %-28s %5d' % (a, n))
print('  --- ЛИЧНЫЕ МОБИЛЬНЫЕ НА ОДНИХ АГРЕГАТОРАХ (до 10, глазами)')
for i, ch, nm, h, u in lich_agr[:10]:
    print('     %-12s %-28s %-13s %-18s %s' % (i, ch, nm, h, u))
print('ИТОГ ' + json.dumps({'личных': sch['ЛИЧНЫХ МОБИЛЬНЫХ всего'],
                            'личных только на агрегаторах':
                                sch['   личный: ВСЕ ссылки — агрегаторы (связь с предприятием не доказана)']},
                           ensure_ascii=False))
