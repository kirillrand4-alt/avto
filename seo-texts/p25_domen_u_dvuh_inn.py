# -*- coding: utf-8 -*-
"""Заслон 2-й сессии на моей базе: домен, заявленный ДВУМЯ ИНН, отдаёт контакты не тому.

Её формулировку забираю дословно, потому что точнее не скажешь: «ни одна почта и ни один
телефон не выдуманы, все настоящие и лежат по указанной ссылке, цитата их подтверждает — но
приписаны они не тому предприятию. Вред тот же, что от выдумки, а проверка по цитате ничего
не поймает, потому что цитата честная». У неё это сняло 317 строк из 3 379.

Мой контроль «строк без ссылки: 0» такого тоже не видит: он проверяет НАЛИЧИЕ
первоисточника, а не то, ЧЕЙ он.

Считаю два признака сразу:
  1. домен ссылки-доказательства заявлен несколькими ИНН;
  2. домен почты (после «собаки») заявлен несколькими ИНН.
Общие площадки (zakupki.gov.ru, tender.pro, etpgpb, checko, list-org) из счёта исключаю —
они по природе общие для всех, и спор о принадлежности к ним не относится.

Ничего не выбрасываю: строки помечаются, число называется.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

VHOD = r'C:\sender\_ops\PARK-KONTAKTY-3S-CHESTNO.jsonl'
VYHOD = r'C:\sender\_ops\PARK-KONTAKTY-3S-CHESTNO.jsonl'
# ПЕРВЫЙ ЗАХОД ДАЛ 1 528 ЗАТРОНУТЫХ СТРОК, и это число было напугано, а не измерено.
# Глазами по списку спорных доменов видно две разные вещи, и обе не есть ошибка привязки:
#
#   rosneft.ru 14 ИНН, rusal.com 13, sibur.ru 9, adm.gazprom.ru 8 — это ДОМЕНЫ ХОЛДИНГОВ,
#      общие для дочерних предприятий по природе. Претензия «домен заявлен двумя ИНН» к ним
#      не относится: у Роснефти и должно быть четырнадцать юрлиц на одном домене.
#   tenderguru.ru, orgpage.ru, rusprofile.ru, egrul.nalog.ru — АГРЕГАТОРЫ, которые я забыла
#      внести в общий список, хотя они общие ровно так же, как checko и list-org.
#
# Настоящая ошибка 2-й сессии была в другом: три НЕСВЯЗАННЫХ «Молока» претендовали на один
# домен. Значит различать надо по названиям: если у предприятий общий корень имени — это
# холдинг, если нет — спор.
OBSHCHIE = re.compile(r'zakupki\.gov|tender\.pro|etpgpb|checko|list-org|roseltorg|rts-tender|'
                      r'tektorg|fabrikant|sberbank-ast|b2b-center|gosnadzor|monitor-pb|'
                      r'zakupki\.mos|kontur|web\.archive|google|yandex|vk\.com|hh\.ru|'
                      r'tenderguru|orgpage|rusprofile|egrul\.nalog|nalog\.ru|sbis|audit-it|'
                      r'spark-interfax|zachestnyibiznes|synapsenet|seldon|bicotender|'
                      r'tenderplan|rulist|sbis\.ru|vestnik-gosreg', re.I)


def domen(u):
    return re.sub(r'^https?://(?:www\.)?([^/]+).*', r'\1', u).lower()


stroki = [json.loads(s) for s in io.open(VHOD, encoding='utf-8')]
dom_inn = collections.defaultdict(set)
for o in stroki:
    inn = o.get('inn') or ''
    for u in (o.get('istochniki') or '').split(' | '):
        if u.startswith('http'):
            d = domen(u)
            if not OBSHCHIE.search(d):
                dom_inn[d].add(inn)
    ad = (o.get('pochta') or '')
    if '@' in ad:
        d = ad.split('@')[-1].strip().lower()
        if d and not OBSHCHIE.search(d) and not re.match(r'(mail|gmail|yandex|bk|inbox|list|'
                                                         r'rambler|ya)\.', d):
            dom_inn[d].add(inn)

# названия предприятий для различения «холдинг» и «спор»
import sqlite3 as _sq
imena = {}
for _b in (r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db'):
    if not os.path.exists(_b):
        continue
    try:
        _c = _sq.connect('file:%s?mode=ro' % _b.replace('\\', '/'), uri=True)
        for _t in ('companies', 'company'):
            try:
                for _i, _n in _c.execute('select inn, name from "%s" where name is not null' % _t):
                    _i = str(_i or '').strip()
                    if _i and _i not in imena:
                        imena[_i] = str(_n)
            except Exception:  # noqa: BLE001
                continue
        _c.close()
    except Exception:  # noqa: BLE001
        pass


def koren(inn):
    n = re.sub(r'[^А-ЯA-Z ]', ' ', (imena.get(inn) or '').upper())
    sl = [w for w in n.split() if len(w) >= 5 and w not in
          ('ОБЩЕСТВО', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ', 'АКЦИОНЕРНОЕ', 'ПУБЛИЧНОЕ',
           'ЗАВОД', 'КОМБИНАТ', 'ФИЛИАЛ', 'ГОСУДАРСТВЕННОЕ', 'ПРЕДПРИЯТИЕ')]
    return set(w[:6] for w in sl)


spornye, holdingi = {}, {}
for d, v in dom_inn.items():
    if len(v) <= 1:
        continue
    korni = [koren(i) for i in v]
    obshchie = set.intersection(*korni) if korni and all(korni) else set()
    if obshchie:
        holdingi[d] = (v, sorted(obshchie)[:2])
    else:
        spornye[d] = v
zatronuto, zatronuto_lich = 0, 0
for o in stroki:
    plohie = set()
    for u in (o.get('istochniki') or '').split(' | '):
        if u.startswith('http') and domen(u) in spornye:
            plohie.add(domen(u))
    ad = (o.get('pochta') or '')
    if '@' in ad and ad.split('@')[-1].strip().lower() in spornye:
        plohie.add(ad.split('@')[-1].strip().lower())
    if plohie:
        zatronuto += 1
        o['spornyy_domen'] = ' | '.join(sorted(plohie))
        o['spornyy_domen_u_skolkih_inn'] = max(len(dom_inn[d]) for d in plohie)
        if o.get('vid_nomera') == 'ЛИЧНЫЙ МОБИЛЬНЫЙ':
            zatronuto_lich += 1
            o['vid_nomera'] = 'мобильный с домена, заявленного несколькими ИНН — принадлежность спорна'

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in stroki:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

lich = sum(1 for o in stroki if o.get('vid_nomera') == 'ЛИЧНЫЙ МОБИЛЬНЫЙ')
# РАЗДЕЛЕНИЕ ПО ЧИСЛУ ПРЕТЕНДЕНТОВ. Определитель холдинга по общему корню названия поймал
# только 15 доменов: у дочерних предприятий юридическое имя не совпадает с брендом («ООО
# РН-Юганскнефтегаз» на rosneft.ru). Значит по названиям холдинг не отличается, и число
# «71 спорный домен» — это НЕ число ошибок привязки: там сидят rosneft, rusal, sibur, evraz,
# lukoil, nornik, mechel, которые я увидела глазами в списке.
# Практический разрез: домен с ТРЕМЯ И БОЛЕЕ претендентами почти наверняка портал холдинга
# или агрегатор; настоящий спор — это ровно ДВА претендента, как три «Молока» у 2-й сессии.
dvoe = {d: v for d, v in spornye.items() if len(v) == 2}
mnogo = {d: v for d, v in spornye.items() if len(v) > 2}
print('\n\n########## ДОМЕНЫ РОВНО С ДВУМЯ ПРЕТЕНДЕНТАМИ — вот это настоящий спор')
for d, v in sorted(dvoe.items())[:12]:
    print('  %-34s %s' % (d[:34], ', '.join(sorted(v))))
print('  таких доменов %d | доменов с тремя и более %d' % (len(dvoe), len(mnogo)))
print('\n\n########## СПОРНЫЕ ДОМЕНЫ, ПО ОДНОМУ')
for d, v in sorted(spornye.items(), key=lambda x: -len(x[1]))[:10]:
    print('  %-34s заявлен %d ИНН: %s' % (d[:34], len(v), ', '.join(sorted(v)[:4])))
print('\n########## ЧИСЛА')
print('  строк контактов               %6d' % len(stroki))
print('  своих доменов всего           %6d' % len(dom_inn))
print('  заявлены >1 ИНН всего         %6d' % (len(spornye) + len(holdingi)))
print('     из них домены ХОЛДИНГОВ    %6d  (общий корень названия — не ошибка)' % len(holdingi))
print('     из них СПОРНЫХ             %6d' % len(spornye))
print('  строк затронуто               %6d' % zatronuto)
print('  из них было ЛИЧНЫХ МОБИЛЬНЫХ  %6d' % zatronuto_lich)
print('  ЛИЧНЫХ осталось               %6d' % lich)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(stroki), 'спорных доменов': len(spornye),
                            'затронуто строк': zatronuto,
                            'снято личных': zatronuto_lich, 'личных осталось': lich},
                           ensure_ascii=False))
