# -*- coding: utf-8 -*-
"""База под Мейер ИЗ ОБЩЕЙ БАЗЫ `park-snimok.db`, а не из своей выборки.

ПОЧЕМУ ПЕРЕСОБРАНО. Первую версию я построил на своих CSV-выгрузках и получил 372
предприятия с 368 ФИО и почти без ролей. Владелец спросил, почему все три сессии смотрят
странные выборки, когда есть общая база. Проверил — он прав, и вот замер:

    моя выборка      372 предприятия, ФИО 368, ролей почти нет
    общая база       297 предприятий В СЕГМЕНТАХ, контактов 3 920, ФИО 1 328, мобильных 320
                     и роли проставлены: главный инженер/механик/энергетик 2 291 по всей базе,
                     снабжение/закупки 19 518, начальник цеха/производства 613

Общая база меньше по числу предприятий в сегментах, но В РАЗЫ богаче по людям — а задача
именно про людей. Строить надо от неё.

ОТКУДА ЧТО БЕРЁТСЯ:
    predpriyatie   имя, регион, ОКВЭД, выручка, статус, лучший человек и телефон
    finansy        выручка с пометкой откуда, ОКВЭД основной и ВСЕ коды
    egrul          адрес, руководитель с должностью, статус
    kontakt        значение, человек, должность, роль, признаки lichnyy/mobilnyy
    contact_source ССЫЛКА и ЦИТАТА под каждое наблюдение — то, ради чего всё и делается

ССЫЛКА ОБЯЗАТЕЛЬНА. Контакт без `source_url` в выдачу не идёт: правило владельца —
каждый контакт доказывается ссылкой, которая ведёт на доказательство. Если у одного
значения несколько наблюдений — это НЕСКОЛЬКО СТРОК, а не склейка через « | »: склейка
теряет, какое поле откуда, и дату наблюдения.

ВЫРУЧКА — КОЛОНКОЙ, НЕ ФИЛЬТРОМ. Прямое условие заказчика: компании с небольшой выручкой
не исключать.
"""
import collections
import csv
import io
import os
import re
import sqlite3
import sys

BAZA = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/park-snimok.db')
VYHOD = sys.argv[2] if len(sys.argv) > 2 else 'PARK-MEYER-BAZA-2S.csv'

# ШИРОКИЙ КОД ЧИТАЕМ ТОЛЬКО КАК ОСНОВНОЙ, УЗКИЙ — ИЗ ЛЮБЫХ. Поймано глазами на выборке
# из девяти строк: в «пищевые» и «экспортёры» заехали НПЗ, Мосводоканал, Газпром трансгаз,
# Златмаш и детский лагерь. Причина измерена: у 147 предприятий в базе больше ДВАДЦАТИ
# кодов ОКВЭД, и раздел 10 целиком или «46.3 оптовая торговля» есть почти у каждого
# крупного — как побочный вид деятельности. Мосводоканал: основной 36.00.1 (водоснабжение),
# Мечел-Энерго: 35.14 (электроэнергия) — в сегмент они попали ИСКЛЮЧИТЕЛЬНО по
# дополнительным кодам.
#   'osnovnoy' — код засчитывается, только если он ОСНОВНОЙ вид деятельности
#   'lyuboy'   — достаточно любого из кодов: код узкий и сам по себе отрасль называет
SEGMENTY = [
    ('экспортёры', [('46.21', 'lyuboy'), ('46.17', 'osnovnoy'), ('46.3', 'osnovnoy'),
                    ('46.11', 'osnovnoy'), ('52.29', 'osnovnoy')], 'добор: признак ВЭД/опта'),
    ('семеноводы', [('01.64', 'lyuboy'), ('01.11', 'osnovnoy'), ('01.13.52', 'lyuboy'),
                    ('01.25.2', 'lyuboy')], 'коды заказчика'),
    ('пищевые', [('10', 'osnovnoy')], 'коды заказчика: весь раздел 10, только основной'),
    ('элеваторы', [('52.10.3', 'lyuboy'), ('01.63', 'lyuboy'), ('10.61', 'lyuboy')],
     'коды заказчика'),
    ('орехи', [('10.39.2', 'lyuboy'), ('01.25.3', 'lyuboy')], 'коды заказчика'),
    ('ягоды', [('01.25.1', 'lyuboy'), ('10.32', 'lyuboy'), ('10.39.2', 'lyuboy')],
     'коды заказчика'),
]

# Приоритет ролей — дословно по заданию. Меньше число = выше в выдаче.
PRIORITET = [
    (1, r'главн\w*\s*инженер|технич|энергетик|механик|директор\s+по\s+производств'),
    (2, r'технолог|качеств|лаборатори|ОТК'),
    (3, r'цеха|производств|элеватор'),
    (4, r'агроном|семеновод'),
    (5, r'снабжен|закупк|тендер|коммерческ'),
    (6, r'руководств|директор|руководител'),
    (8, r'бухгалтер|экономист|кадр'),
]
MOB = re.compile(r'^\+?7?9\d{9}$')


def ves_roli(rol, dolzhnost):
    pole = ' '.join([rol or '', dolzhnost or ''])
    for v, sh in PRIORITET:
        if re.search(sh, pole, re.I):
            return v
    return 9


def main():
    c = sqlite3.connect(BAZA)
    c.row_factory = sqlite3.Row

    # ---- ОКВЭД из двух таблиц: в одной основной, в другой все коды ----------------
    okv = collections.defaultdict(set)
    for r in c.execute("select inn, okved from predpriyatie where okved not in ('', null)"):
        if r['okved']:
            okv[r['inn']].add(str(r['okved']).split()[0])
    okv_vse = {}
    for r in c.execute('select inn, okved, okved_vse from finansy'):
        if r['okved']:
            okv[r['inn']].add(str(r['okved']).split()[0])
        for x in re.findall(r'\d\d\.\d\d(?:\.\d\d?)?', str(r['okved_vse'] or '')):
            okv[r['inn']].add(x)
        if r['okved_vse']:
            okv_vse[r['inn']] = str(r['okved_vse'])[:500]

    def sovpalo(kod, p):
        return kod == p or kod.startswith(p + '.')

    # основной ОКВЭД: из predpriyatie.okved, иначе из finansy.okved
    osnovnoy = {}
    for r in c.execute("select inn, okved from predpriyatie where okved not in ('', null)"):
        if r['okved']:
            osnovnoy[r['inn']] = str(r['okved']).split()[0]
    for r in c.execute('select inn, okved from finansy'):
        if r['okved'] and r['inn'] not in osnovnoy:
            osnovnoy[r['inn']] = str(r['okved']).split()[0]

    segment = collections.defaultdict(list)
    for inn, kody in okv.items():
        osn = osnovnoy.get(inn, '')
        for imya, pravila, _ in SEGMENTY:
            podoshlo = False
            for p, kak in pravila:
                if kak == 'osnovnoy':
                    if osn and sovpalo(osn, p):
                        podoshlo = True
                elif any(sovpalo(k, p) for k in kody if k):
                    podoshlo = True
                if podoshlo:
                    break
            if podoshlo:
                segment[inn].append(imya)
    celi = set(segment)
    if not celi:
        print('ни одно предприятие не попало в сегменты', file=sys.stderr)
        return 1

    # ---- справочные таблицы по целям ---------------------------------------------
    def po_inn(zapros):
        d = {}
        for r in c.execute(zapros):
            if r['inn'] in celi:
                d[r['inn']] = r
        return d

    pred = po_inn('select * from predpriyatie')
    fin = po_inn('select * from finansy')
    egr = po_inn('select * from egrul')

    # ---- наблюдения со ссылкой: ядро выдачи --------------------------------------
    nabl = collections.defaultdict(list)
    for r in c.execute('select * from contact_source'):
        if r['inn'] in celi and (r['source_url'] or '').startswith('http'):
            nabl[r['inn']].append(r)
    # роль и признаки берём из `kontakt` по паре инн+значение
    rol = {}
    for r in c.execute('select * from kontakt'):
        if r['inn'] in celi:
            rol[(r['inn'], (r['znachenie'] or '').strip().lower())] = r

    COLS = ['segment', 'chem_segment', 'nazvanie', 'inn', 'region_gorod', 'adres', 'sayt',
            'okved_osnovnoy', 'okved_dopolnitelnye', 'opisanie_deyatelnosti',
            'vyruchka', 'vyruchka_otkuda', 'ssch', 'status_egrul',
            'fio', 'dolzhnost', 'rol', 'prioritet', 'mobilnyy_pryamoy', 'rabochiy_telefon',
            'email', 'lichnyy', 'istochnik_kontakta', 'ssylka', 'data_nablyudeniya',
            'citata', 'rukovoditel_egrul', 'dolzhnost_rukovoditelya']
    stroki = []
    for inn in sorted(celi):
        p, f, e = pred.get(inn), fin.get(inn), egr.get(inn)
        segs = segment[inn]
        chem = '; '.join(sorted({o for i, pr, o in SEGMENTY if i in segs}))
        obshchee = {
            'segment': ' + '.join(segs), 'chem_segment': chem,
            'nazvanie': (p['nazvanie'] if p else '') or (e['imya'] if e else '')
                        or (f['imya'] if f else ''),
            'inn': inn,
            'region_gorod': (p['region'] if p else '') or (f['region'] if f else ''),
            'adres': e['adres'] if e else '',
            'sayt': '',
            'okved_osnovnoy': (p['okved'] if p else '') or (f['okved'] if f else ''),
            'okved_dopolnitelnye': ' '.join(sorted(okv[inn])),
            'opisanie_deyatelnosti': okv_vse.get(inn, ''),
            'vyruchka': (f['vyruchka'] if f else '') or (p['vyruchka'] if p else ''),
            'vyruchka_otkuda': f['vyruchka_otkuda'] if f else '',
            'ssch': f['ssch'] if f else '',
            'status_egrul': (e['status'] if e else '') or (p['status_egrul'] if p else ''),
            'rukovoditel_egrul': e['rukovoditel'] if e else '',
            'dolzhnost_rukovoditelya': e['dolzhnost_ruk'] if e else '',
        }
        spisok = nabl.get(inn) or []
        if not spisok:
            stroki.append(dict(obshchee, istochnik_kontakta='контакта со ссылкой в базе нет',
                               prioritet=99))
            continue
        for r in spisok:
            zn = (r['znachenie'] or '').strip()
            k = rol.get((inn, zn.lower()))
            dolzh = r['dolzhnost'] or (k['dolzhnost'] if k else '') or ''
            rl = (k['rol'] if k else '') or ''
            cifry = re.sub(r'[^\d+]', '', zn)
            email = zn if '@' in zn else ''
            mob = zn if (MOB.match(cifry) or (k and k['mobilnyy'] == 1 and '@' not in zn)) else ''
            rab = zn if (not email and not mob and len(re.sub(r'\D', '', zn)) >= 6) else ''
            stroki.append(dict(
                obshchee, fio=r['person'] or (k['person'] if k else '') or '',
                dolzhnost=dolzh, rol=rl, prioritet=ves_roli(rl, dolzh),
                mobilnyy_pryamoy=mob, rabochiy_telefon=rab, email=email,
                lichnyy=('да' if (k and k['lichnyy'] == 1) else ''),
                istochnik_kontakta=r['istochnik'] or '',
                ssylka=r['source_url'], data_nablyudeniya=r['data_nablyudeniya'] or '',
                citata=(r['quote'] or '')[:220]))

    stroki.sort(key=lambda s: (s['segment'], s.get('prioritet', 99),
                               0 if s.get('fio') else 1, s['nazvanie']))
    with io.open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for s in stroki:
            w.writerow(s)

    po_seg = collections.Counter()
    for inn, segs in segment.items():
        for s in segs:
            po_seg[s] += 1
    print('предприятий в сегментах: %d | строк: %d' % (len(celi), len(stroki)))
    for k, v in po_seg.most_common():
        print('  %-12s %4d' % (k, v))
    print('строк с ФИО ............', sum(1 for s in stroki if s.get('fio')))
    print('строк с должностью .....', sum(1 for s in stroki if s.get('dolzhnost')))
    print('строк с мобильным ......', sum(1 for s in stroki if s.get('mobilnyy_pryamoy')))
    print('строк с почтой .........', sum(1 for s in stroki if s.get('email')))
    print('БЕЗ ССЫЛКИ .............', sum(1 for s in stroki if s.get('ssylka') == ''))
    pr = collections.Counter(s.get('prioritet') for s in stroki)
    print('по приоритету роли:', dict(sorted(pr.items())))
    print('→', VYHOD)
    return 0


if __name__ == '__main__':
    sys.exit(main())
