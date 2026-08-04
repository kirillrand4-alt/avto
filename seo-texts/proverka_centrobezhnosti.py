# -*- coding: utf-8 -*-
"""Насколько наша метка «центробежная» держится на словах, а не на марках.

Три претензии 3-й сессии, все три проверяются здесь числами, а не спором:

  1. **«Воздуходувка» центробежность НЕ доказывает.** Рутс и вихревые — машины ОБЪЁМНЫЕ,
     а слово одно и то же. Меряем: на скольких наших фактах метка держится ТОЛЬКО на этом
     слове и ни на чём больше.
  2. **Классификатор ложно помечает.** Владелец за полчаса ткнул в три карточки подряд —
     все три помечены центробежными, все три не наша машина. Три из трёх это не случайность.
  3. **Надо перевернуть правило:** «центробежная» только если МАРКА опознана как
     центробежная серия, всё остальное — «тип не установлен», а не «центробежная».
     Просьба прямая: прогнать СТАРУЮ разметку НОВЫМ правилом и сказать, сколько ярлыков
     изменится.

Модуль ничего не меняет в данных. Он только считает и печатает — решение о смене правила
принимается по этим числам, а не до них.

Опознанные центробежные серии берутся из сводного словаря `SLOVAR-MODELEY-SVODNYY.csv`
(11 551 марка, свод пяти словарей 1-й и 3-й сессий с нашими). Сопоставление марки с текстом
идёт ПОСЛЕ нормализации обеих сторон: замер показал 625 марок, которые есть у нас и нет у
соседей только потому, что записаны иначе — «К 250-61-5» против «К-250-61-5».

Использование:
    python3 proverka_centrobezhnosti.py
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
SVOD = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
SLOVAR = os.path.join(C, 'SLOVAR-MODELEY-SVODNYY.csv')
VYHOD = os.path.join(C, 'PROVERKA-centrobezhnosti-po-slovam.csv')

# Слова, на которых у нас держится метка. Разделены НАМЕРЕННО: первые доказывают
# центробежность сами, вторые — нет, и это ровно предмет спора.
DOKAZYVAYUT = ('центробеж', 'турбокомпрессор', 'турбовоздуходув', 'турбоагрегат',
               'турбокомпрессорн')
NE_DOKAZYVAYUT = ('воздуходув', 'компрессор', 'компрессорн', 'нагнетател')
# Прямые признаки ЧУЖОЙ машины: если они есть, метка почти наверняка ложная.
CHUZHIE = ('рутс', 'roots', 'вихрев', 'поршнев', 'винтов', 'мембранн', 'спиральн',
           'вентилятор', 'дымосос', 'аво ', 'воздушного охлаждения')


def norm(m):
    m = (m or '').upper().replace('Ё', 'Е')
    for a, b in (('A', 'А'), ('B', 'В'), ('C', 'С'), ('E', 'Е'), ('H', 'Н'), ('K', 'К'),
                 ('M', 'М'), ('O', 'О'), ('P', 'Р'), ('T', 'Т'), ('X', 'Х'), ('Y', 'У')):
        m = m.replace(a, b)
    return re.sub(r'[^0-9А-Я]', '', m)


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def main():
    slovar = chitat(SLOVAR)
    if not slovar:
        sys.exit(f'ОСТАНОВКА: нет {SLOVAR} — сначала python3 slovar_modeley.py')
    # марки, опознанные как ЦЕНТРОБЕЖНЫЕ, в нормализованном виде
    centro = set()
    for r in slovar:
        tip = (r.get('tip') or '').lower()
        if r.get('nash_profil') == 'да' or 'центробеж' in tip or 'турбовозду' in tip:
            n = norm(r['marka'])
            if len(n) >= 4:
                centro.add(n)
    print(f'словарь: {len(slovar)} марок, опознано центробежными {len(centro)}',
          file=sys.stderr)

    fakty = chitat(SVOD)
    if not fakty:
        sys.exit(f'ОСТАНОВКА: нет {SVOD}')
    print(f'фактов в своде: {len(fakty)}', file=sys.stderr)

    sch = Counter()
    po_predpriyatiyu = defaultdict(Counter)
    spornye = []
    for r in fakty:
        # тексты, по которым вообще принималось решение
        tekst = ' '.join(str(r.get(k) or '') for k in
                         ('predmet', 'citata', 'tip_mashiny', 'marki', 'chem_dokazano')).lower()
        marki_txt = str(r.get('marki') or '')
        est_marka = any(norm(m) in centro for m in re.split(r'[;,|]', marki_txt)
                        if len(norm(m)) >= 4)
        est_dokaz = any(s in tekst for s in DOKAZYVAYUT)
        est_slabo = any(s in tekst for s in NE_DOKAZYVAYUT)
        est_chuzhoe = any(s in tekst for s in CHUZHIE)
        pomecheno = 'центробеж' in str(r.get('tip_mashiny') or '').lower()
        if not pomecheno:
            sch['не помечено центробежной'] += 1
            continue
        sch['помечено центробежной'] += 1
        if est_marka:
            sch['держится на ОПОЗНАННОЙ МАРКЕ'] += 1
            vid = 'марка опознана'
        elif est_dokaz:
            sch['держится на слове, доказывающем центробежность'] += 1
            vid = 'слово доказывает'
        elif est_slabo:
            sch['ДЕРЖИТСЯ ТОЛЬКО НА СЛАБОМ СЛОВЕ'] += 1
            vid = 'только слабое слово'
        else:
            sch['не держится ни на чём из перечисленного'] += 1
            vid = 'основание не найдено'
        if est_chuzhoe:
            sch['И ПРИ ЭТОМ ЕСТЬ ПРИЗНАК ЧУЖОЙ МАШИНЫ'] += 1
        if vid in ('только слабое слово', 'основание не найдено') or est_chuzhoe:
            po_predpriyatiyu[r.get('inn') or ''][vid] += 1
            if len(spornye) < 100000:
                spornye.append({'inn': r.get('inn') or '',
                                'predpriyatie': (r.get('predpriyatie') or '')[:60],
                                'na_chem_derzhitsya': vid,
                                'priznak_chuzhoy_mashiny': 'да' if est_chuzhoe else '',
                                'marki': marki_txt[:80],
                                'tip_mashiny': (r.get('tip_mashiny') or '')[:60],
                                'predmet': (r.get('predmet') or '')[:200],
                                'citata': (r.get('citata') or '')[:200]})

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['inn', 'predpriyatie', 'na_chem_derzhitsya',
                                          'priznak_chuzhoy_mashiny', 'marki', 'tip_mashiny',
                                          'predmet', 'citata'],
                           delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(spornye)

    vsego = sch['помечено центробежной']
    print('\n=== ОТВЕТ НА ПРЕТЕНЗИЮ 3-й СЕССИИ ===', file=sys.stderr)
    for k, v in sch.most_common():
        dolya = f' — {v * 100 // vsego} % помеченных' if vsego and 'не помечено' not in k else ''
        print(f'  {k}: {v}{dolya}', file=sys.stderr)
    slabo = sch['ДЕРЖИТСЯ ТОЛЬКО НА СЛАБОМ СЛОВЕ'] + sch['не держится ни на чём из перечисленного']
    if vsego:
        print(f'\nЕСЛИ ПЕРЕВЕРНУТЬ ПРАВИЛО (центробежная только по опознанной марке), '
              f'ярлык сменится у {vsego - sch["держится на ОПОЗНАННОЙ МАРКЕ"]} фактов из '
              f'{vsego} — это {(vsego - sch["держится на ОПОЗНАННОЙ МАРКЕ"]) * 100 // vsego} %',
              file=sys.stderr)
        print(f'ПОД ПОДОЗРЕНИЕМ СЕЙЧАС: {slabo} фактов на {len(po_predpriyatiyu)} '
              f'предприятиях → {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
