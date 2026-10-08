# -*- coding: utf-8 -*-
"""Статистика панели Meyer по компаниям: откуда, ЛПР, выручка, сегменты, продавцы, статусы.
Только чтение (каталог и продажи открываются read-only). Итог – JSON на дроп и печать."""
import collections
import io
import json
import re
import sqlite3

KAT = r'C:\centro2\data\meyer_baza1.db'
SALES = r'C:\centro2\data\centro_sales_meyer1.db'
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
komp = [dict(r) for r in k.execute('select * from company')]
kont = collections.defaultdict(list)
for r in k.execute('select inn, phone_type, has_role, nomer_ne_lichnyy, person, role from contact'):
    kont[r['inn']].append(dict(r))
naz = dict(s.execute('select inn, username from company_assignment'))
fio = dict(s.execute("select username, coalesce(fio, username) from users"))
sost = {}
for inn, u, rez in s.execute('select inn, username, call_result from company_state'):
    if naz.get(inn) == u:
        sost[inn] = rez


def lpr_vid(c):
    ks = kont[c['inn']]
    lpr = [x for x in ks if x['has_role'] and not (x['nomer_ne_lichnyy'] or '').strip()
           and (x['role'] or '') not in ('', 'общий номер', 'приёмная', 'общий номер холдинга', 'общий/приёмная')]
    if any(x['phone_type'] == 'мобильный' for x in lpr):
        return 'ЛПР: мобильный'
    if any(x['phone_type'] == 'рабочий с добавочным' for x in lpr):
        return 'ЛПР: рабочий с добавочным'
    if lpr:
        return 'ЛПР: рабочий'
    return 'без ЛПР (общие/прочие номера)'


def vyr_gr(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '0 неизвестна'
    if v <= 0:
        return '0 неизвестна'
    return ('5 от 5 млрд' if v >= 5e9 else '4 1,5–5 млрд' if v >= 1.5e9 else '3 300 млн–1,5 млрд' if v >= 3e8
            else '2 100–300 млн' if v >= 1e8 else '1 до 100 млн')


def baza(c):
    return ' + '.join(sorted(b.strip() for b in (c.get('bazy') or '').split('|') if b.strip())) or 'без метки'


out = {'vsego': len(komp)}
t = collections.defaultdict(collections.Counter)
vyr_sum = collections.defaultdict(list)
for c in komp:
    b = baza(c)
    t['baza'][b] += 1
    t['baza_lpr'][(b, lpr_vid(c))] += 1
    t['baza_vyr'][(b, vyr_gr(c.get('vyruchka_rub')))] += 1
    t['lpr'][lpr_vid(c)] += 1
    t['vyr'][vyr_gr(c.get('vyruchka_rub'))] += 1
    try:
        if float(c.get('vyruchka_rub') or 0) > 0:
            vyr_sum[b].append(float(c['vyruchka_rub']))
    except ValueError:
        pass
    for sg in (c.get('segment') or 'не указан').split('|'):
        t['segment'][sg.strip()] += 1
    t['bitrix'][('да' if c.get('bitrix_kc') else 'нет')] += 1
    t['holding'][('в группе' if c.get('holding_gruppa') else 'одна')] += 1
    t['fio'][('есть ЛПР с ФИО' if (c.get('lpr_s_fio') or 0) else 'нет')] += 1
    u = fio.get(naz.get(c['inn']), naz.get(c['inn']) or 'без продавца')
    t['prodavec'][u] += 1
    t['prodavec_baza'][(u, b)] += 1
    t['prodavec_lpr'][(u, lpr_vid(c))] += 1
    t['status'][sost.get(c['inn'], 'new')] += 1
    t['region'][(c.get('region') or 'не указан')] += 1
    t['poyas'][c.get('chas_poyas') or 3] += 1
med = {b: sorted(v)[len(v) // 2] / 1e6 for b, v in vyr_sum.items() if v}
lines = []


def p(x=''):
    lines.append(x)


p('ВСЕГО КОМПАНИЙ: %d' % len(komp))
p('\nПО ИСТОЧНИКУ (метке базы):')
for b, n in t['baza'].most_common():
    p('  %-22s %4d | медиана выручки %6.0f млн' % (b, n, med.get(b, 0)))
    for vid in ('ЛПР: мобильный', 'ЛПР: рабочий с добавочным', 'ЛПР: рабочий', 'без ЛПР (общие/прочие номера)'):
        if t['baza_lpr'][(b, vid)]:
            p('      %-32s %4d' % (vid, t['baza_lpr'][(b, vid)]))
p('\nЛПР ВСЕГО:')
for vid, n in sorted(t['lpr'].items()):
    p('  %-32s %4d' % (vid, n))
p('  с ФИО ЛПР: %d' % t['fio']['есть ЛПР с ФИО'])
p('\nВЫРУЧКА (группы):')
for g, n in sorted(t['vyr'].items()):
    p('  %-22s %4d   по базам: %s' % (g[2:], n, ', '.join('%s %d' % (b, t['baza_vyr'][(b, g)]) for b in t['baza'] if t['baza_vyr'][(b, g)])))
p('\nСЕГМЕНТЫ (компания с двумя считается в обоих):')
for sg, n in t['segment'].most_common():
    p('  %-26s %4d' % (sg, n))
p('\nБИТРИКС КЦ: %d да / %d нет; в группе-холдинге: %d' % (t['bitrix']['да'], t['bitrix']['нет'], t['holding']['в группе']))
p('\nПО ПРОДАВЦАМ:')
for u, n in sorted(t['prodavec'].items()):
    p('  %-20s %4d | %s | %s' % (u, n, ', '.join('%s %d' % (b, t['prodavec_baza'][(u, b)]) for b in t['baza'] if t['prodavec_baza'][(u, b)]),
                                  ', '.join('%s %d' % (v.replace('ЛПР: ', ''), t['prodavec_lpr'][(u, v)]) for v in sorted(t['lpr']) if t['prodavec_lpr'][(u, v)])))
p('\nСТАТУСЫ: %s' % dict(t['status']))
p('ЧАСОВЫЕ ПОЯСА (смещение от UTC): %s' % dict(sorted(t['poyas'].items())))
p('РЕГИОНОВ: %d, верх: %s' % (len(t['region']), t['region'].most_common(8)))
txt = '\n'.join(lines)
io.open(r'C:\seostat\drop\drop-storage\centro2-stat-paneli.txt', 'w', encoding='utf-8').write(txt)
print(txt)
