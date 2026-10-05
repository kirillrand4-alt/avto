# -*- coding: utf-8 -*-
"""Отбор базы Мейера ПО РОЛЯМ: только те, кто влияет на закупку, эксплуатацию и качество.

ТРЕБОВАНИЕ ЗАКАЗЧИКА ДОСЛОВНО: «Нужны не общие телефоны и не секретари, а по возможности
прямые контакты сотрудников, влияющих на закупку, эксплуатацию и требования к качеству
оборудования». Списки ролей заданы ПО СЕГМЕНТАМ и в каждом свои — поэтому отбор идёт не
одним общим фильтром, а по сегменту строки.

РЕЗЕРВ ТОЛЬКО ДЛЯ ЭЛЕВАТОРОВ, и это тоже дословное условие: «Если прямых контактов этих
специалистов нет — допускаются другие сотрудники, через которых можно выйти на ЛПР,
включая бухгалтерию». Поэтому элеватор, у которого не нашлось ни одной целевой роли,
отдаётся с резервными строками и пометкой `rezerv=да`. Для остальных сегментов такого
условия не было — там резерва нет.

ЧТО ВЫБРАСЫВАЕТСЯ ВСЕГДА: приёмная, секретарь, канцелярия, справочная, диспетчерская,
колл-центр, общий телефон и почта организации без человека.

ОРЕХИ И ЯГОДЫ заказчик списком ролей не описал. Они целиком внутри раздела 10 (переработка),
поэтому к ним применён список ПИЩЕВЫХ — это помечено в колонке `chem_otbor`, чтобы решение
было видно и его можно было поменять одним словом.

Отброшенные строки НЕ удаляются насовсем: они уходят в `PARK-MEYER-OTSEV-2S.csv`. Удалять
доказательство ради красивой витрины нельзя — фильтр обратим, удаление нет.
"""
import collections
import csv
import io
import re
import sys

VHOD = sys.argv[1] if len(sys.argv) > 1 else 'engineers-lens/PARK-MEYER-BAZA-2S.csv'
VYHOD = sys.argv[2] if len(sys.argv) > 2 else 'engineers-lens/PARK-MEYER-LPR-2S.csv'
OTSEV = 'engineers-lens/PARK-MEYER-OTSEV-2S.csv'

# Роли по сегментам — дословно из задания заказчика.
PISHCHEVYE = (r'генеральн\w*\s*директор|исполнительн\w*\s*директор|^директор\b|\bдиректор\b|'
              r'главн\w*\s*инженер|техническ\w*\s*директор|директор\s+по\s+производств|'
              r'главн\w*\s*технолог|технолог|директор\s+по\s+качеств|'
              r'(?:руководител\w*|специалист\w*|начальник\w*)[^.;]{0,25}качеств|'
              r'качеств|лаборатори|ОТК|'
              r'закупк|снабжен|тендер|МТО|материально-техническ')
ELEVATORY = (r'\bдиректор\b|генеральн\w*\s*директор|главн\w*\s*инженер|главн\w*\s*технолог|'
             r'заведующ\w+[^.;]{0,25}(?:элеватор|производств)|управляющ\w+[^.;]{0,20}элеватор|'
             r'начальник\w*[^.;]{0,20}(?:элеватор|производств)|агроном|'
             r'закупк|снабжен|тендер')
SEMENOVODY = (r'\bдиректор\b|генеральн\w*\s*директор|главн\w*\s*агроном|агроном|'
              r'руководител\w*[^.;]{0,25}производств|начальник\w*[^.;]{0,20}производств|'
              r'семеновод|селекцион|главн\w*\s*инженер|закупк|снабжен|тендер')
EKSPORTERY = (r'руководител|\bдиректор\b|генеральн\w*\s*директор|коммерческ\w*\s*директор|'
              r'закупк|снабжен|тендер|производств|качеств|лаборатори|агроном|'
              r'главн\w*\s*инженер|техническ\w*\s*директор|главн\w*\s*технолог|технолог')

PRAVILA = [
    ('элеваторы', ELEVATORY, 'список заказчика для элеваторов'),
    ('семеноводы', SEMENOVODY, 'список заказчика для семеноводов'),
    ('экспортёры', EKSPORTERY, 'список заказчика для экспортёров'),
    ('пищевые', PISHCHEVYE, 'список заказчика для пищевых'),
    ('орехи', PISHCHEVYE, 'список пищевых: орехи целиком в разделе 10, своего списка не было'),
    ('ягоды', PISHCHEVYE, 'список пищевых: ягоды целиком в разделе 10, своего списка не было'),
]
# Выбрасывается всегда, в любом сегменте.
NIKOGDA = re.compile(r'приёмн|приемн|секретар|канцеляр|справочн|диспетчерск|колл-?центр|'
                     r'call-?centre|call-?center|общий телефон|телефон организации|'
                     r'почта организации|не определена|должность не названа', re.I)
# Резерв элеватора: через этих людей можно выйти на ЛПР.
REZERV = re.compile(r'бухгалтер|главбух|экономист|кадр|юрист|офис-менеджер|менеджер', re.I)


# ПРИВЯЗКА К ПРЕДПРИЯТИЮ. Поймано глазами на выборке: контакты приезжали к ЧУЖОМУ ИНН.
#   ООО «Сандугач» (мукомольное, 10.61) — директор и «начальник ЛДП» с сайта школы-тёзки
#     sandugachschool.obr.site;
#   сельский ГУП — главный инженер АО «Петербургский тракторный завод» с kirovets-ptz.com
#     и приёмная комиссия университета с mkgtu.ru;
#   prodoctorov.ru — справочник врачей.
# Замер на 461 строке: реестр/первоисточник 347, название предприятия в цитате 49, имя в
# домене 23, источник не подтверждён 42. Из 42 часть — собственные сайты, записанные
# АББРЕВИАТУРОЙ (ПАО «НКХП» -> novoroskhp.ru), и транслит их не ловит.
# Решение: ЯВНО чужие источники — в отсев с причиной; сомнительные — в выдачу с пометкой
# `privyazka`, а не молча. Удалять или оставлять наугад — одинаково плохо.
CHUZHIE_ISTOCHNIKI = re.compile(
    r'kirovets-ptz\.com|mkgtu\.ru|prodoctorov\.ru|obr\.site|\.edu\.ru|school|shkol|'
    r'detsad|licey|gimnaz|bolnic|poliklin|zoon\.ru|2gis|yell\.ru', re.I)
PERVOISTOCHNIK = re.compile(r'zakupki\.gov\.ru|egrul\.nalog\.ru|gosnadzor\.ru|nalog\.ru|'
                            r'checko\.ru|e-disclosure\.ru|rts-tender\.ru|b2b-center\.ru|'
                            r'roseltorg\.ru|sberbank-ast\.ru|etpgpb\.ru', re.I)
STOP_IMYA = {'ооо', 'оао', 'зао', 'пао', 'гуп', 'муп', 'фгуп', 'общество', 'ограниченной',
             'ответственностью', 'акционерное', 'открытое', 'закрытое', 'публичное',
             'государственное', 'унитарное', 'предприятие', 'сельскохозяйственное',
             'компания', 'завод', 'комбинат', 'фирма', 'группа', 'птицефабрика'}
TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщыэюя',
              ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n',
               'o', 'p', 'r', 's', 't', 'u', 'f', 'h', 'ts', 'ch', 'sh', 'sch', 'y', 'e',
               'yu', 'ya']))


def privyazka(r):
    ssylka = r.get('ssylka') or ''
    dom = re.sub(r'^https?://(www\.)?', '', ssylka).split('/')[0].lower()
    if CHUZHIE_ISTOCHNIKI.search(dom):
        return 'чужой'
    if PERVOISTOCHNIK.search(dom):
        return 'реестр/первоисточник'
    t = [w for w in re.findall(r'[а-яё]{4,}', (r.get('nazvanie') or '').lower())
         if w not in STOP_IMYA]
    cit = (r.get('citata') or '').lower()
    if t and any(w[:6] in cit for w in t):
        return 'название в цитате'
    if t and any(''.join(TR.get(c, c) for c in w)[:4] in dom.replace('-', '') for w in t):
        return 'свой сайт (имя в домене)'
    return 'не подтверждена названием — проверить'


def pole(r):
    return ' '.join([r.get('rol') or '', r.get('dolzhnost') or ''])


def main():
    rows = list(csv.DictReader(io.open(VHOD, encoding='utf-8-sig'), delimiter=';'))
    cols = list(rows[0].keys()) + ['chem_otbor', 'rezerv', 'privyazka']
    po_inn = collections.defaultdict(list)
    for r in rows:
        po_inn[r['inn']].append(r)

    ostavleno, otseyano = [], []
    for inn, spisok in po_inn.items():
        seg = (spisok[0].get('segment') or '')
        # Если предприятие попало в несколько сегментов, применяем САМЫЙ ШИРОКИЙ из них:
        # сузить всегда успеем, а потерять человека из-за порядка строк нельзя.
        shablony = [(imya, sh, pochemu) for imya, sh, pochemu in PRAVILA if imya in seg]
        if not shablony:
            shablony = [('пищевые', PISHCHEVYE, 'сегмент не распознан — список пищевых')]
        celevye = []
        for r in spisok:
            t = pole(r)
            if not t.strip() or NIKOGDA.search(t):
                otseyano.append(dict(r, chem_otbor='общий контакт, секретарь или роль не названа'))
                continue
            pv = privyazka(r)
            if pv == 'чужой':
                otseyano.append(dict(r, chem_otbor='контакт с сайта ДРУГОЙ организации'))
                continue
            podoshlo = [(i, p) for i, sh, p in shablony if re.search(sh, t, re.I)]
            if podoshlo:
                celevye.append(dict(r, chem_otbor=podoshlo[0][1], rezerv='', privyazka=pv))
            else:
                otseyano.append(dict(r, chem_otbor='роль вне списка сегмента'))
        if celevye:
            ostavleno.extend(celevye)
        elif 'элеваторы' in seg:
            # Дословное условие заказчика: у элеватора без прямых контактов допускаются
            # другие сотрудники, включая бухгалтерию.
            rez = [r for r in spisok if REZERV.search(pole(r))]
            for r in rez:
                ostavleno.append(dict(r, rezerv='да',
                                      chem_otbor='резерв элеватора: прямых ЛПР не нашлось'))

    for put, dannye in ((VYHOD, ostavleno), (OTSEV, otseyano)):
        with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
            w.writeheader()
            for r in sorted(dannye, key=lambda x: (x.get('segment', ''),
                                                   int(x.get('prioritet') or 99),
                                                   0 if x.get('fio') else 1)):
                w.writerow(r)

    print('было строк %d | ОСТАВЛЕНО %d | отсеяно %d' % (len(rows), len(ostavleno), len(otseyano)))
    print('предприятий: было %d | осталось %d' % (len(po_inn), len({r['inn'] for r in ostavleno})))
    seg = collections.Counter(r['segment'] for r in ostavleno)
    for k, v in seg.most_common():
        print('  %-24s строк %4d | предприятий %3d'
              % (k, v, len({r['inn'] for r in ostavleno if r['segment'] == k})))
    print('с ФИО ............', sum(1 for r in ostavleno if r.get('fio')))
    print('с мобильным ......', sum(1 for r in ostavleno if r.get('mobilnyy_pryamoy')))
    print('с почтой .........', sum(1 for r in ostavleno if r.get('email')))
    print('резерв элеваторов ', sum(1 for r in ostavleno if r.get('rezerv') == 'да'))
    print('привязка:', dict(collections.Counter(r.get('privyazka', '') for r in ostavleno)))
    print('отсеяно как ЧУЖОЙ источник:',
          sum(1 for r in otseyano if 'ДРУГОЙ' in (r.get('chem_otbor') or '')))
    pr = collections.Counter(int(r.get('prioritet') or 99) for r in ostavleno)
    print('по приоритету:', dict(sorted(pr.items())))
    print('→', VYHOD, '\n→', OTSEV)


if __name__ == '__main__':
    sys.exit(main())
