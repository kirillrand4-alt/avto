# -*- coding: utf-8 -*-
"""Чистка `plany-zakupki.csv`: ключ совпал не с предметом закупки, а с названием проекта.

Дефект нашла соседняя сессия на своей стороне, я проверил на своём файле и подтвердил.
В планах закупки 223-ФЗ к предмету каждой позиции дописывается название инвестиционного
проекта: «…**в рамках реализации проекта «Реконструкция… с заменой турбоагрегатов…»**».
Поиск по слову ловит этот хвост, и вся программа проекта попадает в выдачу целиком.

Живой замер: у АО «Усть-СреднеканГЭСстрой» (ИНН 4909095279) по ключу «турбоагрегат» лежат
**563 позиции**, среди которых сварочные технологии, трубопроводы, чугунные трубы, генераторы
огнетушащего аэрозоля и пневмокаркасный ангар. Ни одна не про турбоагрегат.

Второй дефект той же выгрузки: **«турбокомпрессор» — чаще всего автомобильный турбонаддув.**
Отсекается по соседству со словами про двигатель внутреннего сгорания и марки техники, но
осторожно: «в комплекте с электродвигателем» — это наша машина, а не автомобильная.

Что делает скрипт: режет хвост от «в рамках»/«в рамках реализации проекта» и заново проверяет,
остался ли ключ в самом предмете. Строки, потерявшие ключ, помечаются и выносятся отдельно —
не удаляются молча, потому что удалять молча нельзя: пропажу видно, а подделку нет.

Использование:
    python3 plany_chistka.py [--vhod <csv>] [--vyhod <csv>]
"""
import csv
import os
import re
import sys
from collections import Counter

BAZA = os.path.dirname(os.path.abspath(__file__))
VHOD = os.path.join(BAZA, 'engineers-lens', 'centro', 'plany-zakupki.csv')
VYHOD = os.path.join(BAZA, 'engineers-lens', 'centro', 'plany-zakupki-chistye.csv')

# Хвост с названием проекта. Именно «в рамках» — самая частая связка; «по объекту» и
# «для нужд объекта» встречаются реже, но ведут себя так же.
HVOST = re.compile(r'\s+(?:в\s+рамках|в\s+составе\s+проекта|по\s+объекту[:\s]|'
                   r'для\s+нужд\s+объекта)\b.*$', re.I | re.S)
# Автомобильный турбонаддув. «электродвигател» специально НЕ ловится: «турбокомпрессор в
# комплекте с электродвигателем» — наша машина.
AVTO = re.compile(r'\bТКР\b|турбонаддув|для\s+двигател|дизел\w*\s+двигат|двигател\w*\s+'
                  r'(?:Deutz|Cummins|ЯМЗ|КАМАЗ|MAN)|ЯМЗ|КАМАЗ|МАЗ|тепловоз|автосамосвал|БелАЗ',
                  re.I)
# Ключ «центробежный» сам по себе ловит насосы — их у нас не продают.
NASOS = re.compile(r'насос', re.I)


def osnova(klyuch):
    """Обрубок ключа для проверки вхождения: «турбоагрегат» → «турбоагрегат», «компрессорная» →
    «компрессорн». Обрезаем только окончание, а не до основы: на Tender.pro обрезанная основа
    в ЗАПРОСЕ давала ноль, но здесь это проверка вхождения в уже полученный текст, не запрос."""
    k = klyuch.strip().lower()
    return k[:-2] if k.endswith(('ый', 'ая', 'ое', 'ые', 'ой')) else k


def main():
    vhod = sys.argv[sys.argv.index('--vhod') + 1] if '--vhod' in sys.argv else VHOD
    vyhod = sys.argv[sys.argv.index('--vyhod') + 1] if '--vyhod' in sys.argv else VYHOD
    rows = list(csv.DictReader(open(vhod, encoding='utf-8-sig'), delimiter=';'))
    cols = list(rows[0].keys()) + ['predmet_bez_proekta', 'brak']

    sch = Counter()
    for r in rows:
        p = r.get('predmet') or ''
        chistyy = HVOST.sub('', p).strip()
        r['predmet_bez_proekta'] = chistyy
        kl = osnova(r.get('klyuch') or '')
        brak = ''
        if kl and kl in p.lower() and kl not in chistyy.lower():
            brak = 'ключ только в названии проекта'
        elif 'турбокомпрессор' in chistyy.lower() and AVTO.search(chistyy):
            brak = 'автомобильный турбонаддув'
        elif kl == 'центробежн' and NASOS.search(chistyy):
            brak = 'центробежный насос, не компрессор'
        r['brak'] = brak
        sch[brak or 'годно'] += 1

    with open(vyhod, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)

    godnye = [r for r in rows if not r['brak']]
    vpered = [r for r in godnye if (r.get('data_v_budushchem') or '').strip() in ('1', 'да', 'True')]
    print(f'строк всего: {len(rows)}')
    for k, v in sch.most_common():
        print(f'  {k}: {v}')
    print(f'годных строк: {len(godnye)}, разных ИНН: {len({r["inn"] for r in godnye if r["inn"]})}')
    print(f'из них с датой размещения в будущем: {len(vpered)}, '
          f'разных ИНН: {len({r["inn"] for r in vpered if r["inn"]})}')
    print(f'→ {vyhod}')


if __name__ == '__main__':
    main()
