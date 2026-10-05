# -*- coding: utf-8 -*-
"""База Мейера «до человека»: только МОБИЛЬНЫЙ или РАБОЧИЙ С ДОБАВОЧНЫМ, ведущий к ЛПР.

ТРЕБОВАНИЕ ЗАКАЗЧИКА: оставить только мобильные либо рабочие с добавочным, которые ведут
к нужному человеку. Общий телефон приёмной — мимо, почта — мимо, рабочий без добавочного —
мимо: по нему попадаешь на секретаря.

ОТКУДА БЕРЁМ:
  1) строки витрины ЛПР (PARK-MEYER-LPR-2S.csv), где номер уже стоит в строке человека;
  2) ЦИТАТЫ из общей базы `contact_source.quote` — там часто лежит целый список сотрудников:
     «Заместитель директора по коммерческим вопросам Казанский Андрей Рудольфович.
      +7(831)2289080 доб.212 glsnab@mkvolod.ru. Кудинов Роман Валентинович. …»
     База привязала к людям не всё, что в этих списках есть. Снимаем пары «человек —
     его номер» прямо из текста, по правилу близости.

ПРАВИЛО БЛИЗОСТИ — главная защита. Номер принадлежит человеку, только если стоит ПОСЛЕ его
ФИО не дальше 70 знаков и МЕЖДУ ними нет другого ФИО. Иначе это номер соседа по списку.
Добавочный засчитывается, только если идёт сразу за номером (≤ 12 знаков).

ЗАСЛОН ОТ ТЁЗОК. Поймано на этой же выборке: мобильный «Ерофеева А. А.» взят с
prodoctorov.ru (врач в Воронеже) и с сайта стоматологии, а привязан к АО «Ерофеев».
Источники-справочники врачей, школ, вузов — в отсев.
"""
import collections
import csv
import io
import os
import re
import sqlite3
import sys

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
BAZA = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/park-snimok.db')
VHOD = os.path.join(L, 'PARK-MEYER-LPR-2S.csv')
VYHOD = os.path.join(L, 'PARK-MEYER-DOZVON-2S.csv')

MOB = re.compile(r'^\+?7?9\d{9}$')
NOMER = re.compile(r'(\+?[78][\s(\-]*\d{3,4}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2})')
DOB = re.compile(r'^\W{0,4}(?:доб\.?|добавочн\w*|вн\.?|внутр\w*|ext\.?)\s*[:#№]?\s*(\d{2,5})', re.I)
FIO = re.compile(r'([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}'
                 r'(?:ович|евич|ьевич|овна|евна|ична|инична))')
CHUZHIE = re.compile(r'prodoctorov|stomat|obr\.site|\.edu\.|school|shkol|mkgtu|'
                     r'kirovets-ptz|bolnic|poliklin|vrach|doctor|med\w*\.ru', re.I)
DOLZH = re.compile(
    r'(генеральн\w+\s+директор\w*|исполнительн\w+\s+директор\w*|техническ\w+\s+директор\w*|'
    r'главн\w+\s+(?:инженер|технолог|механик|энергетик|агроном)\w*|'
    r'заместител\w+\s+директора\s+по\s+[а-я]+\s*[а-я]*|директор\w*\s+по\s+[а-я]+|'
    r'начальник\w*\s+[а-я]+(?:\s+[а-я]+)?|заведующ\w+\s+[а-я]+|руководител\w*\s+[а-я]+|'
    r'технолог\w*|агроном\w*|специалист\w*\s+по\s+[а-я]+|менеджер\w*\s+по\s+закупк\w*|'
    r'\bдиректор\b)', re.I)
CEL = re.compile(r'директор|инженер|технолог|механик|энергетик|агроном|качеств|лаборатор|'
                 r'производств|элеватор|цех|закупк|снабжен|тендер|коммерческ|семеновод', re.I)


def tsifry(s):
    return re.sub(r'\D', '', s or '')


def main():
    L_ = list(csv.DictReader(io.open(VHOD, encoding='utf-8-sig'), delimiter=';'))
    po_inn = collections.defaultdict(list)
    for r in L_:
        po_inn[r['inn']].append(r)
    inny = set(po_inn)
    karta = {r['inn']: r for r in L_}

    vyhod, vidal = [], set()

    def dobavit(baza, fio, dolzh, mob, rab, dob, ssylka, citata, otkuda):
        # Ключ по ПОСЛЕДНИМ 10 цифрам: «+7978 730 59 59» и «9787305959» — один номер,
        # и в первой сборке он лёг двумя строками.
        k = (baza['inn'], fio, tsifry(mob or rab)[-10:], dob)
        if k in vidal:
            return
        vidal.add(k)
        vyhod.append({
            'segment': baza.get('segment', ''), 'nazvanie': baza.get('nazvanie', ''),
            'inn': baza['inn'], 'region_gorod': baza.get('region_gorod', ''),
            'okved_osnovnoy': baza.get('okved_osnovnoy', ''),
            'vyruchka': baza.get('vyruchka', ''), 'fio': fio, 'dolzhnost': dolzh,
            'mobilnyy': mob, 'rabochiy_telefon': rab, 'dobavochnyy': dob,
            'ssylka': ssylka, 'citata': citata[:240], 'otkuda': otkuda})

    # 1) мобильные из витрины ЛПР
    for r in L_:
        if (r.get('mobilnyy_pryamoy') and not CHUZHIE.search(r.get('ssylka') or '')
                and (r.get('dolzhnost') or r.get('rol'))):
            dobavit(r, r.get('fio', ''), r.get('dolzhnost') or r.get('rol', ''),
                    r['mobilnyy_pryamoy'], '', '', r.get('ssylka', ''), r.get('citata', ''),
                    'витрина ЛПР: мобильный в строке человека')

    # 2) пары «человек — номер — добавочный» прямо из цитат общей базы
    c = sqlite3.connect(BAZA)
    c.row_factory = sqlite3.Row
    for row in c.execute('select inn, source_url, quote from contact_source'):
        if row['inn'] not in inny:
            continue
        url = row['source_url'] or ''
        if not url.startswith('http') or CHUZHIE.search(url):
            continue
        q = ' '.join((row['quote'] or '').split())
        if not q:
            continue
        lyudi = [(m.start(), m.end(), m.group(1)) for m in FIO.finditer(q)]
        for i, (s, e, fio) in enumerate(lyudi):
            granica = lyudi[i + 1][0] if i + 1 < len(lyudi) else len(q)
            hvost = q[e:min(granica, e + 70)]
            m = NOMER.search(hvost)
            if not m:
                continue
            nomer = m.group(1).strip()
            d = DOB.match(hvost[m.end():m.end() + 14])
            dob = d.group(1) if d else ''
            cif = tsifry(nomer)
            mob = nomer if MOB.match('+' + cif if not cif.startswith('+') else cif) \
                or (len(cif) == 11 and cif[1] == '9') or (len(cif) == 10 and cif[0] == '9') else ''
            if not mob and not dob:
                continue          # рабочий без добавочного ведёт к секретарю — мимо
            # должность: перед именем (до 90 знаков) или сразу после
            pered = q[max(0, s - 90):s]
            dm = list(DOLZH.finditer(pered)) or list(DOLZH.finditer(q[e:e + 60]))
            dolzh = ' '.join(dm[-1].group(1).split()) if dm else ''
            # Без названной должности номер НЕ доказан как ведущий к нужному человеку.
            # Поймано на выборке: «Чернова И. Г., доб.105» стоит в списке со страницы
            # бухгалтерии — роль не названа, и заявлять её ЛПР нельзя.
            if not dolzh or not CEL.search(dolzh):
                continue
            dobavit(karta[row['inn']], fio, dolzh, mob, '' if mob else nomer, dob, url,
                    q[max(0, s - 90):e + 80], 'цитата базы: номер за ФИО, правило близости')

    COLS = ['segment', 'nazvanie', 'inn', 'region_gorod', 'okved_osnovnoy', 'vyruchka',
            'fio', 'dolzhnost', 'mobilnyy', 'rabochiy_telefon', 'dobavochnyy',
            'ssylka', 'citata', 'otkuda']
    with io.open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(vyhod, key=lambda x: (x['segment'], x['nazvanie'], x['fio'])):
            w.writerow(r)

    print('строк до человека: %d | предприятий: %d | людей: %d'
          % (len(vyhod), len({r['inn'] for r in vyhod}),
             len({(r['inn'], r['fio']) for r in vyhod})))
    print('  мобильный ............ %d' % sum(1 for r in vyhod if r['mobilnyy']))
    print('  рабочий + добавочный . %d' % sum(1 for r in vyhod if r['dobavochnyy']))
    print('  с должностью ......... %d' % sum(1 for r in vyhod if r['dolzhnost']))
    print('  откуда:', dict(collections.Counter(r['otkuda'] for r in vyhod)))
    print('→', VYHOD)


if __name__ == '__main__':
    main()
