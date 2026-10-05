# -*- coding: utf-8 -*-
"""БАЗА ПОД МЕЙЕР из уже собранного: шесть сегментов по ОКВЭД, контакты со ссылкой.

ОТКУДА ДАННЫЕ. Всё из своего корпуса, ничего не доспрашивается:
  PARK-VYDACHA-PREDPRIYATIYA-2S.csv  сайт, выручка, ОКВЭД (все коды), адрес, руководитель
  PARK-VYDACHA-KONTAKTY-2S.csv       телефоны, почты, люди — у каждой строки ссылка и цитата
  PARK-OKVED-2S.jsonl                коды с названиями -> «описание деятельности»
  PARK-DADATA-2S.jsonl               ЕГРЮЛ: адрес (регион/город), статус, руководитель

ЧЕСТНАЯ ГРАНИЦА, названная до выдачи. Корпус собран от реестра ЭПБ, то есть это
предприятия, У КОТОРЫХ ЕСТЬ КОМПРЕССОРНОЕ ОБОРУДОВАНИЕ. Для Мейера это не минус, а
отбор: завод с компрессорной уже имеет инженерную службу и бюджет на оборудование.
Но полным списком отрасли эта выборка НЕ является и выдаваться за него не должна.

СЕГМЕНТЫ. Коды заказчика плюс добор, помеченный отдельно (`kody_dobavleny`):
  экспортёры  признак ВЭД/оптовых операций: 46.21* (зерно), 46.17*, 46.3*, 46.11*,
              52.29* (ТЭО) — у экспортёров ОКВЭД экспорта как такового нет
  семеноводы  01.64, 01.11*, 01.13.52, 01.25.2
  пищевые     весь раздел 10
  элеваторы   52.10.3, 01.63, 10.61*
  орехи       10.39.2, 01.25.3
  ягоды       01.25.1, 10.32* (+10.39.2 пересекается с орехами — так и помечаем)

ПРИОРИТЕТ КОНТАКТОВ. Роли ранжируются по заданию: технические и производственные выше
закупок, закупки выше общих, секретарь и бухгалтерия — ниже всех, но НЕ выбрасываются:
по условию «если прямых контактов нет — допускаются другие, включая бухгалтерию».
Удалять доказательство ради красивой витрины нельзя, поэтому роль — пометка, а не фильтр.

ВЫРУЧКА НЕ КРИТЕРИЙ ОТБОРА — отдельной колонкой, как просили, никого по ней не отсеиваем.
"""
import collections
import csv
import io
import json
import os
import re
import sys

L = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(L, 'engineers-lens')

SEGMENTY = [
    ('экспортёры', ['46.21', '46.17', '46.3', '46.11', '52.29'], 'добор: признак ВЭД/опта'),
    ('семеноводы', ['01.64', '01.11', '01.13.52', '01.25.2'], 'коды заказчика'),
    ('пищевые', ['10'], 'коды заказчика: весь раздел 10'),
    ('элеваторы', ['52.10.3', '01.63', '10.61'], 'коды заказчика'),
    ('орехи', ['10.39.2', '01.25.3'], 'коды заказчика'),
    ('ягоды', ['01.25.1', '10.32', '10.39.2'], 'коды заказчика'),
]

# Роли по заданию, в порядке приоритета. Чем меньше число, тем выше в выдаче.
ROLI = [
    (1, 'техн. руководитель', r'главн\w+\s+инженер|техническ\w+\s+директор|главн\w+\s+механик|'
                              r'главн\w+\s+энергетик|директор\s+по\s+производств'),
    (2, 'технолог/качество', r'главн\w+\s+технолог|технолог\b|директор\s+по\s+качеств|'
                             r'начальник\w*\s+(?:отдела\s+)?качеств|специалист\w*\s+по\s+качеств|'
                             r'лаборатори|ОТК'),
    (3, 'производство/элеватор', r'начальник\w*\s+производств|заведующ\w+\s+элеватор|'
                                 r'заведующ\w+\s+производств|начальник\w*\s+цеха|'
                                 r'управляющ\w+\s+элеватор'),
    (4, 'агроном/семеноводство', r'агроном|семеновод|селекцион'),
    (5, 'закупки', r'закупк|снабжен|тендер|МТО|материально-техническ|коммерческ\w+\s+директор'),
    (6, 'руководитель', r'генеральн\w+\s+директор|директор\b|руководител'),
    (8, 'бухгалтерия/прочее', r'бухгалтер|главбух|экономист|кадр'),
    (9, 'приёмная/общий', r'приёмн|приемн|секретар|канцеляр|справочн'),
]
MOBILNYY = re.compile(r'^\+?7?9\d{9}$')


def jl(imya):
    p = os.path.join(L, imya)
    if not os.path.exists(p):
        return []
    out = []
    for s in io.open(p, encoding='utf-8'):
        s = s.strip()
        if s:
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    return out


def cs(imya):
    p = os.path.join(L, imya)
    return list(csv.DictReader(io.open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def kody_predpriyatiya(x):
    k = set((x.get('okved_kody') or '').split())
    o = (x.get('okved_osnovnoy') or '').split(' ')[0].strip()
    if o:
        k.add(o)
    return {c for c in k if c}


def podhodit(kod, prefiksy):
    for p in prefiksy:
        if kod == p or kod.startswith(p + '.'):
            return True
        if p == '10' and (kod == '10' or kod.startswith('10.')):
            return True
    return False


def rol_i_ves(dolzhnost, chelovek, citata):
    pole = ' '.join([dolzhnost or '', citata or ''])
    for ves, imya, shablon in ROLI:
        if re.search(shablon, dolzhnost or '', re.I):
            return ves, imya, 'должность названа прямо'
    # Признак рядом с именем, а не где-то на странице: роль страницы — не роль человека
    if chelovek and citata and chelovek.split()[0] in citata:
        i = citata.index(chelovek.split()[0])
        ryadom = citata[max(0, i - 90):i + 90]
        for ves, imya, shablon in ROLI:
            if re.search(shablon, ryadom, re.I):
                return ves, imya, 'признак рядом с именем в цитате'
    return 9, 'не определена', ''


def main():
    pred = {x['inn']: x for x in cs('PARK-VYDACHA-PREDPRIYATIYA-2S.csv') if x.get('inn')}
    for x in jl('PARK-DADATA-2S.jsonl'):
        if x.get('inn') in pred:
            pred[x['inn']].setdefault('adres', x.get('address', ''))
            pred[x['inn']].setdefault('status_egrul', x.get('status', ''))
    opisanie = {}
    for x in jl('PARK-OKVED-2S.jsonl'):
        if x.get('okved_all'):
            opisanie[x['inn']] = x['okved_all'][:400]

    # сегменты
    segment = collections.defaultdict(list)
    for inn, x in pred.items():
        k = kody_predpriyatiya(x)
        if not k:
            continue
        for imya, pref, otkuda in SEGMENTY:
            if any(podhodit(c, pref) for c in k):
                segment[inn].append(imya)

    kont = collections.defaultdict(list)
    for r in cs('PARK-VYDACHA-KONTAKTY-2S.csv'):
        if r.get('inn') in segment and (r.get('ssylka') or '').startswith('http'):
            kont[r['inn']].append(r)

    KCOLS = ['segment', 'nazvanie', 'inn', 'region_gorod', 'sayt', 'okved_osnovnoy',
             'okved_dopolnitelnye', 'opisanie_deyatelnosti', 'vyruchka', 'vyruchka_god',
             'status_egrul', 'fio', 'dolzhnost', 'rol', 'prioritet', 'mobilnyy_pryamoy',
             'rabochiy_telefon', 'email', 'istochnik_kontakta', 'ssylka', 'citata',
             'chem_rol']
    stroki = []
    for inn, segs in segment.items():
        x = pred[inn]
        adr = x.get('adres') or ''
        region = adr.split(',')[0].strip() if adr else ''
        obshchee = {
            'segment': ' + '.join(segs),
            'nazvanie': x.get('nazvanie_egrul') or x.get('predpriyatie') or '',
            'inn': inn,
            'region_gorod': region or adr,
            'sayt': x.get('sayt', ''),
            'okved_osnovnoy': x.get('okved_osnovnoy', ''),
            'okved_dopolnitelnye': x.get('okved_kody', ''),
            'opisanie_deyatelnosti': opisanie.get(inn, ''),
            'vyruchka': x.get('vyruchka', ''),
            'vyruchka_god': x.get('vyruchka_god', ''),
            'status_egrul': x.get('status_egrul', ''),
        }
        spisok = kont.get(inn) or []
        if not spisok:
            # Предприятие без контакта — строка всё равно нужна: сегмент и ОКВЭД доказаны,
            # контакт добирается следующим заходом. Пустое поле честнее выдуманного.
            stroki.append(dict(obshchee, istochnik_kontakta='контакта в базе нет',
                               ssylka=x.get('ssylka_checko', ''), prioritet=99))
            continue
        for r in spisok:
            ves, rol, chem = rol_i_ves(r.get('dolzhnost'), r.get('chelovek'), r.get('citata'))
            zn = (r.get('znachenie') or '').strip()
            cifry = re.sub(r'[^\d+]', '', zn)
            email = zn if '@' in zn else ''
            mob = zn if MOBILNYY.match(cifry) else ''
            rab = zn if (not email and not mob and re.sub(r'\D', '', zn)[-10:].isdigit()
                         and len(re.sub(r'\D', '', zn)) >= 6) else ''
            stroki.append(dict(obshchee, fio=r.get('chelovek', ''),
                               dolzhnost=r.get('dolzhnost', ''), rol=rol, prioritet=ves,
                               mobilnyy_pryamoy=mob, rabochiy_telefon=rab, email=email,
                               istochnik_kontakta=r.get('istochnik', ''),
                               ssylka=r.get('ssylka', ''), citata=(r.get('citata') or '')[:200],
                               chem_rol=chem))

    stroki.sort(key=lambda s: (s['segment'], s.get('prioritet', 99), s['nazvanie']))
    put = os.path.join(L, 'PARK-MEYER-BAZA-2S.csv')
    with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=KCOLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for s in stroki:
            w.writerow(s)

    print('предприятий в сегментах: %d | строк контактов: %d' % (len(segment), len(stroki)))
    po_seg = collections.Counter()
    for inn, segs in segment.items():
        for s in segs:
            po_seg[s] += 1
    for k, v in po_seg.most_common():
        skonk = len({i for i in segment if k in segment[i] and kont.get(i)})
        print('  %-14s предприятий %4d | из них с контактом %4d' % (k, v, skonk))
    rol_sch = collections.Counter(s.get('rol', '') for s in stroki if s.get('rol'))
    print('роли:', dict(rol_sch.most_common(9)))
    print('строк с мобильным:', sum(1 for s in stroki if s.get('mobilnyy_pryamoy')))
    print('строк с почтой:', sum(1 for s in stroki if s.get('email')))
    print('строк с ФИО:', sum(1 for s in stroki if s.get('fio')))
    print('→', put)


if __name__ == '__main__':
    sys.exit(main())
