# -*- coding: utf-8 -*-
"""Свод словарей моделей компрессоров и слова для обхода площадок.

Пункт 9 владельца: «запишите все уже известные нам модели центробежных компрессоров, которые
встречались за всё время, и используйте их для опознавания среды, подходит нам компания или
нет, а также прогона по площадкам».

ЧЕСТНО, ПОЧЕМУ МОДУЛЬ ТАКОЙ. Сначала он был РАЗБОРЩИКОМ: собрать марки и отправить
провайдеру на классификацию. Владелец указал, что соседи это давно сделали, и он прав — на
дропе лежал не один файл, а пять, и вместе они богаче того, что я собирался получить. Разбор
остановлен на 40 марках, модуль переписан из «разбирать» в «свести и применить».
Правило владельца из VSEM-SESSIYAM: «спросили — перепроверили — использовали».
Перепроверил числами, они ниже.

ЧТО ЛЕЖАЛО У СОСЕДЕЙ (замерено, а не пересказано):
    SLOVAR-MODELEY-1s.csv                    424 марки: тип, среда, серия, завод,
                                             откуда известно и ССЫЛКА НА ПАСПОРТ
    SLOVAR-MODELEY-1s-NEOPOZNANNYE.csv     8 168 марок, признанных неопознанными
    SLOVAR-MODELEY-1s-RAZOBRANO-...csv       300 разобранных провайдером
    SREDA-po-markam.csv                    2 058 марок → среда с обоснованием
    VAZHNOE-3s-SLOVAR-MAROK.csv               39 марок 3-й сессии со счётом воздух/газ
    SLOVAR-MODELEY-1s-NASHI-DLYA-PLOSHCHADOK.txt  179 обозначений, отобранных для поиска

ПОКРЫТИЕ. Наших отобранных марок 2 978, соседские словари покрывают 1 199 — 40 %. Оставшиеся
1 779 это «12», «25», «К-0», «PN 8», «В 2021», то есть шум разбора, а не модели. По настоящим
моделям чужой словарь задачу закрывает, и мой разбор потратил бы квоту на классификацию
мусора. Это и есть цена того, что я не спросил соседей до того, как писать.

ЧТО ДЕЛАЕТ МОДУЛЬ:
  1. сводит пять чужих словарей и наши марки в один файл с провенансом — у каждой строки
     видно, кто её знает и откуда;
  2. отмечает, какие марки годятся КАК ПОИСКОВЫЕ СЛОВА для обхода площадок. Это третья
     часть пункта 9 и единственный вход к предприятиям, которых у нас ещё нет: обход по
     нашему списку ИНН структурно не может найти новое предприятие, он читает нашу очередь;
  3. считает, скольким предприятиям очереди словарь мог бы поставить среду.

Использование:
    python3 slovar_modeley.py
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'
VYHOD = os.path.join(C, 'SLOVAR-MODELEY-SVODNYY.csv')
SLOVA = os.path.join(C, 'SLOVA-DLYA-OBHODA-PLOSHCHADOK.txt')
ISHODNIKI = ['OCHERED-centrobezhnye.csv', 'SVOD-tri-sostoyaniya.csv',
             'SVOD-POLNYY-po-predpriyatiyam.csv']
COLS = ['marka', 'nash_profil', 'tip', 'sreda', 'seriya', 'proizvoditel', 'pochemu',
        'nashih_upominaniy', 'nashih_predpriyatiy', 'znayut', 'ssylka',
        'godno_kak_slovo_poiska']

# Чужие словари. Порядок важен: первый, кто знает марку, задаёт её разбор, остальные только
# добавляются в колонку «знают». Первым идёт самый подробный.
CHUZHIE = [
    ('1s-разобрано', 'SLOVAR-MODELEY-1s.csv'),
    ('3s-словарь', 'VAZHNOE-3s-SLOVAR-MAROK.csv'),
    ('1s-среда', 'SREDA-po-markam.csv'),
    ('1s-провайдером', 'SLOVAR-MODELEY-1s-RAZOBRANO-PROVAYDEROM.csv'),
    ('1s-неопознанные', 'SLOVAR-MODELEY-1s-NEOPOZNANNYE.csv'),
]
SPISOK_1S = 'SLOVAR-MODELEY-1s-NASHI-DLYA-PLOSHCHADOK.txt'


def chitat(put, kol='marka'):
    if not os.path.exists(put):
        return {}
    out = {}
    for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
        m = (r.get(kol) or '').strip()
        if m:
            out.setdefault(m, r)
    return out


def nashi_marki():
    upom = Counter()
    pred = defaultdict(set)
    for f in ISHODNIKI:
        p = os.path.join(L, f)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            for m in re.split(r'[;,|]', r.get('marki') or r.get('marka') or ''):
                m = m.strip()
                if len(m) >= 2:
                    upom[m] += 1
                    if r.get('inn'):
                        pred[m].add(r['inn'])
    return upom, pred


def main():
    upom, pred = nashi_marki()
    slovari = [(imya, chitat(os.path.join(RAB, f))) for imya, f in CHUZHIE]
    net = [f for (imya, f), (_, d) in zip(CHUZHIE, slovari) if not d]
    if net:
        sys.exit('ОСТАНОВКА: не скачаны словари соседей: ' + ', '.join(net) +
                 '\n  bash server/drop_client.sh down <имя>\n'
                 '  Собирать без них — снова делать чужую работу с нуля.')

    put_slov = os.path.join(RAB, SPISOK_1S)
    gotovye = set()
    if os.path.exists(put_slov):
        gotovye = {s.strip() for s in open(put_slov, encoding='utf-8') if s.strip()}

    vse = set(gotovye)
    for _, d in slovari:
        vse |= set(d)
    vse |= {m for m in upom if len(pred.get(m, ())) > 1}

    sch = {'строк': 0, 'наш профиль': 0, 'годно как слово': 0, 'знает только сосед': 0,
           'знаем только мы': 0}
    f = open(VYHOD, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    w.writeheader()
    slova = []
    for m in sorted(vse):
        znayut, r = [], {}
        for imya, d in slovari:
            if m in d:
                znayut.append(imya)
                if not r:
                    r = d[m]
        if m in gotovye:
            znayut.append('1s-список-для-площадок')
        nashi_u, nashi_p = upom.get(m, 0), len(pred.get(m, ()))
        if not znayut and nashi_p:
            sch['знаем только мы'] += 1
        if znayut and not nashi_u:
            sch['знает только сосед'] += 1
        profil = (r.get('nash_profil') or '').strip()
        tip = (r.get('tip') or r.get('chto') or '').strip()
        sreda = (r.get('sreda') or '').strip()
        if profil == 'да':
            sch['наш профиль'] += 1
        # Слово годится для поиска на площадке, только если это ОПОЗНАННАЯ модель нашего
        # профиля, а не позиционное обозначение: иначе обход пойдёт искать закупки по номеру
        # аппарата с чужой схемы и вернёт мусор под видом находок.
        godno = 'да' if (m in gotovye or profil == 'да') and len(m) >= 4 else ''
        if godno:
            sch['годно как слово'] += 1
            slova.append(m)
        w.writerow({'marka': m, 'nash_profil': profil, 'tip': tip[:120], 'sreda': sreda[:60],
                    'seriya': (r.get('seriya') or '')[:60],
                    'proizvoditel': (r.get('otkuda') or '')[:80],
                    'pochemu': (r.get('pochemu') or r.get('priznak') or '')[:200],
                    'nashih_upominaniy': nashi_u, 'nashih_predpriyatiy': nashi_p,
                    'znayut': ', '.join(znayut) or 'только наша база',
                    'ssylka': (r.get('ssylka') or '')[:200],
                    'godno_kak_slovo_poiska': godno})
        sch['строк'] += 1
    f.close()

    # ВАРИАНТЫ НАПИСАНИЯ. Замер по нашей базе: из 1 736 марок, которых нет у соседей, 625 —
    # это те же модели, записанные иначе (К 250-61-5 против К-250-61-5, ТВ80-1 против ТВ-80-1,
    # ТВ-80-1.6 против ТВ-80-1,6). У 16 из них наш профиль, и на них приходится 462 упоминания,
    # которые поиск по одной канонической записи не найдёт. Поэтому в список для площадок
    # каждое слово кладётся во всех формах разделителя: площадка ищет подстроку, а не модель.
    formy = []
    for m in slova:
        vidy = {m, m.replace('-', ' '), m.replace('-', ''), m.replace(',', '.')}
        vidy |= {v.replace(',', '.') for v in list(vidy)}
        formy.extend(v for v in vidy if len(v) >= 4)
    formy = sorted(set(formy))
    open(SLOVA, 'w', encoding='utf-8').write('\n'.join(formy) + '\n')
    sch['слов с вариантами написания'] = len(formy)
    print(f'сведено: {sch}', file=sys.stderr)
    print(f'→ {VYHOD}\n→ {SLOVA}', file=sys.stderr)

    # Сколько предприятий очереди словарь мог бы закрыть по среде.
    och = list(csv.DictReader(open(os.path.join(L, 'OCHERED-centrobezhnye.csv'),
                                   encoding='utf-8-sig'), delimiter=';'))
    sreda_po_marke = {}
    for _, d in slovari:
        for m, r in d.items():
            s = (r.get('sreda') or '').strip()
            if s and m not in sreda_po_marke:
                sreda_po_marke[m] = s
    bez_sredy = moglo = 0
    for r in och:
        if (r.get('sreda_dokazana') or '').strip():
            continue
        bez_sredy += 1
        for m in re.split(r'[;,|]', r.get('marki') or ''):
            if sreda_po_marke.get(m.strip()):
                moglo += 1
                break
    print(f'предприятий очереди без доказанной среды: {bez_sredy}, из них словарь мог бы '
          f'дать среду по марке: {moglo}', file=sys.stderr)


if __name__ == '__main__':
    main()
