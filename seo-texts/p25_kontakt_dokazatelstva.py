# -*- coding: utf-8 -*-
"""Доказательства контакта: считать ТОЛЬКО настоящие ссылки. И заслон «номер не личный».

Первый заход показал свёртку 11 351 -> 2 468 телефонов, и глазами на верхушке видно две
вещи, которых счётчик не сказал:

1. В поле ссылки лежат НЕ ССЫЛКИ: «Центр ТендерПро-Консультант, круглосуточно (приёмная)»,
   «Контактное лицо по техническим вопросам, вн. 4617», «По вопросам тендера». Если считать
   их доказательствами, сила контакта надувается прозой.
2. У одного номера бывает 25 РАЗНЫХ ИМЁН (ИНН 7718560636, +78002506834, 26 ссылок,
   25 имён; +74952151438 — 19 ссылок, 18 имён, среди них «Благодарим Вас» и
   «Поставщиков Вопросы», которые вообще не люди). Это линия, а не человек.

Отсюда правило, которое я кладу рядом с правилом владельца «доказательств столько, сколько
уникальных ссылок»: **много имён на одном номере = номер НЕ личный.** Это тот же заслон,
что «номер у нескольких предприятий», только внутри одного предприятия.

Считаю распределение и печатаю в КОНЦЕ. Только чтение.
"""
import collections
import json
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
URL = re.compile(r'https?://', re.I)
NE_CHELOVEK = re.compile(r'вопрос|благодар|поставщик|отдел|служб|приёмн|приемн|центр|'
                         r'консультант|тендер|контакт', re.I)


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kol = [r[1] for r in cx.execute('pragma table_info(kontakty_svod)')]
sel = ','.join('"%s"' % k for k in kol)
pu = [k for k in kol if 'url' in k.lower() or 'ssyl' in k.lower() or k.lower() == 'source']
pt = [k for k in kol if 'phone' in k.lower() or 'tel' in k.lower()]
pe = [k for k in kol if 'mail' in k.lower()]

tel = collections.defaultdict(lambda: {'ssylki': set(), 'proza': set(), 'imena': set()})
em = collections.defaultdict(lambda: {'ssylki': set(), 'proza': set(), 'imena': set()})
for r in cx.execute('select %s from kontakty_svod' % sel):
    d = dict(zip(kol, r))
    inn = str(d.get('inn') or '').strip()
    if not inn:
        continue
    ist = [str(d.get(k)).strip() for k in pu if d.get(k)]
    ssyl = [s for s in ist if URL.search(s)]
    proza = [s for s in ist if not URL.search(s)]
    imya = str(d.get('person') or '').strip()
    for k in pt:
        c = desyat(d.get(k))
        if c:
            z = tel[(inn, c)]
            z['ssylki'].update(ssyl); z['proza'].update(proza)
            if imya:
                z['imena'].add(imya)
    for k in pe:
        e = str(d.get(k) or '').strip().lower()
        if '@' in e:
            z = em[(inn, e)]
            z['ssylki'].update(ssyl); z['proza'].update(proza)
            if imya:
                z['imena'].add(imya)
cx.close()

print('\n\n########## ЧИСЛА')
print('  строк в kontakty_svod                 11351 (замерено ранее)')
print('  РАЗНЫХ телефонов (ИНН + 10 цифр)      %6d' % len(tel))
print('  РАЗНЫХ почт (ИНН + адрес)             %6d' % len(em))

for imya, d in (('ТЕЛЕФОНЫ', tel), ('ПОЧТЫ', em)):
    print('\n  === %s: сколько НАСТОЯЩИХ ссылок у контакта' % imya)
    r = collections.Counter(min(len(v['ssylki']), 10) for v in d.values())
    for k in sorted(r):
        print('      ссылок %-4s контактов %5d' % ('10+' if k == 10 else k, r[k]))
    print('      без единой ссылки, только проза: %d'
          % sum(1 for v in d.values() if not v['ssylki'] and v['proza']))
    print('      без ссылки и без прозы:          %d'
          % sum(1 for v in d.values() if not v['ssylki'] and not v['proza']))
    ri = collections.Counter(min(len(v['imena']), 6) for v in d.values())
    print('  === %s: сколько ИМЁН на одном контакте (>1 = не личный)' % imya)
    for k in sorted(ri):
        print('      имён %-4s контактов %5d' % ('6+' if k == 6 else k, ri[k]))
    lich = sum(1 for v in d.values() if len(v['imena']) == 1 and v['ssylki'])
    print('      ЛИЧНЫЙ И ДОКАЗАННЫЙ (одно имя + хоть одна ссылка): %d' % lich)
    musor = sum(1 for v in d.values()
                if any(NE_CHELOVEK.search(x) for x in v['imena']))
    print('      среди имён есть не-человек («вопросы», «отдел», «благодарим»): %d' % musor)

print('ИТОГ ' + json.dumps({'телефонов': len(tel), 'почт': len(em)}, ensure_ascii=False))
