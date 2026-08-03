# -*- coding: utf-8 -*-
"""Обратный аудит сбора: чем собраны данные, которые у нас лежат, и не устарел ли способ.

Пункт 16 владельца: «посмотреть какие данные сейчас собраны, и шаг за шагом идти назад отвечая
на вопрос: всеми ли возможными способами был сделан сбор, есть инструменты которые были но мы
про них забыли, тянем ли мы мусор, есть ли инструменты которые мы уже доработали, но у нас
остались данные которыми были собраны старым методом».

Проверка механическая, а не на память, потому что память подводит: за сутки инструменты
правились десять раз, и какой файл каким прогоном получен — по головам не восстановишь.

Три вопроса, три раздела:

ОГОВОРКА, НАЙДЕННАЯ ПЕРВЫМ ЖЕ ПРОГОНОМ. Сравнение по времени изменения врёт сразу после
`git checkout`: восстановление ветки ставит всем файлам одно время, и данные выглядят «на минуту
старше кода», хотя собраны тем же кодом. Разрыв меньше десяти минут поэтому не считается
устареванием, а печатается отдельной пометкой. Надёжны только два вывода этого раздела: «файла
нет вовсе» и разрыв в часы. Само правило про восстановление ветки — из опыта: контейнер за сутки
перезапускался четырежды.

1. **УСТАРЕЛ ЛИ СПОСОБ.** Для каждого файла данных сравниваем его время с временем последней
   правки кода, который его порождает. Файл старше своего инструмента — данные собраны прежней
   версией, и всё, что мы с тех пор починили, к ним не применилось. Это самый частый случай
   тихой потери: инструмент починен, а данные остались старыми, и по числам не видно.

2. **ЗАБЫТЫЕ ИНСТРУМЕНТЫ.** Скрипт есть, а его выходного файла нет или он старше суток —
   значит инструмент написан и брошен. Такие находятся: за ночь их набралось несколько.

3. **ТЯНЕМ ЛИ МУСОР.** Доля отсева в очереди и сколько предприятий держится на слабейшем
   доказательстве.

Использование:
    python3 obratnyy_audit.py
"""
import csv
import os
import time
from collections import Counter

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'

# файл данных → скрипт, который его порождает
CEPOCHKA = [
    ('SVOD-tri-sostoyaniya.csv', L, 'svod_tri_sostoyaniya.py'),
    ('SVOD-POLNYY-po-predpriyatiyam.csv', L, 'svod_polnyy.py'),
    ('OCHERED-centrobezhnye.csv', L, 'tip_mashiny.py'),
    # Пишет его proverka_otseva.py, а не tip_mashiny.py: аудит советовал пересобрать
    # не тем инструментом. Найдено разбором модулей 03.08.
    ('OTSEV-tip-mashiny.csv', L, 'proverka_otseva.py'),
    ('SVODNAYA-centrobezhnye.csv', L, 'svodnaya_centrobezhnye.py'),
    ('VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv', L, 'sborka_dlya_paneli.py'),
    ('HARAKTERISTIKI-mashin-po-predpriyatiyam.csv', L, 'harakteristiki_mashin.py'),
    ('SREDA-po-markam.csv', L, 'sreda_dobor.py'),
    ('PROVERKA-otseva.md', L, 'proverka_otseva.py'),
    ('centro/lica-s-sajtov.csv', L, 'lica_so_stranic.py'),
    ('centro/lica-s-sajtov-otsev.csv', L, 'lica_so_stranic.py'),
    ('centro/poteryannye-inn.csv', L, 'dadata_inn.py'),
    ('centro/eis/skany-lica.csv', L, 'skany_provajderom.py'),
]

# инструмент → его выходной файл (проверяем, не брошен ли инструмент)
INSTRUMENTY = [
    ('vlozheniya.py', os.path.join(C, 'eis', 'vlozheniya-lica.csv'), 'вложения закупок ЕИС'),
    ('skany_provajderom.py', os.path.join(C, 'eis', 'skany-lica.csv'), 'сканы протоколов глазами модели'),
    # Имя выхода было неверным, из-за чего инструмент вечно числился брошенным.
    ('novosti_dokazatelstva.py', os.path.join(L, 'DOKAZATELSTVA-iz-novostey.csv'),
     'новости как доказательство'),
    ('tender_centro_scan.py', os.path.join(C, 'tenderpro', 'tp-spisok.csv'), 'обход Tender.pro'),
    ('erknm_harvest.py', os.path.join(C, 'istochnik-erknm-nashi-347.csv'), 'проверки Ростехнадзора'),
    ('nzl_referencii.py', os.path.join(C, 'istochnik-nzl-referencii-kompressory.csv'), 'референс-лист НЗЛ'),
    ('lica_so_stranic.py', os.path.join(C, 'lica-s-sajtov.csv'), 'люди со страниц сайтов'),
    ('sajty_po_ocheredi.py', os.path.join(RAB, 'sajty_OCHERED_centrobezhnye_csv.jsonl'), 'поиск сайтов'),
    ('dadata_inn.py', os.path.join(C, 'poteryannye-inn.csv'), 'разрешение названий в ИНН'),
]

CHUZHIE = [('TEHLPR-VSE-s-provenansom.csv', 'люди 1-й сессии'),
           ('OBHOD-kontakty-3s.csv', 'контакты с обхода 3-й сессии'),
           ('BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv', 'общая база 3-й сессии')]


def vozrast(p):
    return (time.time() - os.path.getmtime(p)) / 3600 if os.path.exists(p) else None


def strok(p):
    if not os.path.exists(p):
        return 0
    try:
        return sum(1 for _ in open(p, encoding='utf-8-sig', errors='replace')) - 1
    except OSError:
        return 0


def main():
    print('=' * 96)
    print('1. УСТАРЕЛ ЛИ СПОСОБ: данные старше своего инструмента = собраны прежней версией')
    print('=' * 96)
    ustarelo = []
    for fajl, papka, skript in CEPOCHKA:
        pd = os.path.join(papka, fajl)
        ps = os.path.join(BAZA, skript)
        if not os.path.exists(pd):
            print(f'  НЕТ ФАЙЛА   {fajl:<48} (порождает {skript})')
            ustarelo.append((fajl, skript, 'файла нет вовсе'))
            continue
        if not os.path.exists(ps):
            continue
        vd, vs = os.path.getmtime(pd), os.path.getmtime(ps)
        if vd < vs:
            razryv = (vs - vd) / 60
            if razryv < 10:      # см. оговорку про git checkout в шапке
                print(f'  ровесники   {fajl:<48} разрыв {razryv:.0f} мин — это восстановление ветки')
                continue
            print(f'  СТАРЫЕ      {fajl:<48} на {razryv/60:.1f} ч старше {skript}')
            ustarelo.append((fajl, skript, f'старше кода на {razryv/60:.1f} ч'))
        else:
            print(f'  свежие      {fajl:<48} {strok(pd):>7} строк')

    print()
    print('=' * 96)
    print('2. ЗАБЫТЫЕ ИНСТРУМЕНТЫ: скрипт есть, а выхода нет или он старше суток')
    print('=' * 96)
    zabyto = []
    for skript, vyhod, opis in INSTRUMENTY:
        v = vozrast(vyhod)
        if v is None:
            print(f'  БРОШЕН      {skript:<32} {opis:<38} выхода НЕТ')
            zabyto.append((skript, opis, 'выхода нет'))
        elif v > 24:
            print(f'  ЗАСТОЯЛСЯ   {skript:<32} {opis:<38} выход {v:.0f} ч назад, {strok(vyhod)} строк')
            zabyto.append((skript, opis, f'выход {v:.0f} ч назад'))
        else:
            print(f'  работает    {skript:<32} {opis:<38} {strok(vyhod):>7} строк, {v:.1f} ч назад')

    print()
    print('=' * 96)
    print('3. ЧУЖИЕ ФАЙЛЫ: не выросли ли у соседей с тех пор, как я их брал')
    print('=' * 96)
    for f, opis in CHUZHIE:
        p = os.path.join(RAB, f)
        if os.path.exists(p):
            print(f'  {strok(p):>7} строк  {f:<42} {opis}')
        else:
            print(f'  НЕТ         {f:<42} {opis} — скачать с дропа')

    print()
    print('=' * 96)
    print('4. ТЯНЕМ ЛИ МУСОР: чем держится очередь')
    print('=' * 96)
    po = os.path.join(L, 'OCHERED-centrobezhnye.csv')
    if os.path.exists(po):
        rows = list(csv.DictReader(open(po, encoding='utf-8-sig'), delimiter=';'))
        tipy = Counter((r.get('tipy_mashin') or '').split(' | ')[0] for r in rows)
        print(f'  предприятий в очереди: {len(rows)}')
        for k, v in tipy.most_common(6):
            print(f'     {v:>5}  {k[:60]}')
        bez_tel = sum(1 for r in rows if not (r.get('telefony_predpriyatiya') or '').strip())
        bez_sajta = sum(1 for r in rows if not (r.get('sayt') or '').strip())
        print(f'  без телефона: {bez_tel}, без сайта: {bez_sajta}')
    otsev = os.path.join(L, 'OTSEV-tip-mashiny.csv')
    if os.path.exists(otsev):
        print(f'  в корзине строк: {strok(otsev)}')

    print()
    print('=' * 96)
    print('ИТОГ К ДЕЙСТВИЮ')
    print('=' * 96)
    if not ustarelo and not zabyto:
        print('  всё свежее, брошенных инструментов нет')
    for f, s, p in ustarelo:
        print(f'  ПЕРЕСОБРАТЬ  {f:<48} {p}')
    for s, o, p in zabyto:
        print(f'  ЗАПУСТИТЬ    {s:<32} {o:<38} {p}')


if __name__ == '__main__':
    main()
