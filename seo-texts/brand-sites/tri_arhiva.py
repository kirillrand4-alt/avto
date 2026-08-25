#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Три среза пакета под разные решения владельца.

    python3 tri_arhiva.py

  1-dorogie-planovye   Станции: МКС, компрессорные, азотные, кислородные.
                       Раздела на сайте нет - его надо создавать. Дорого
                       по сделке и дорого по работе.
  2-est-kategoriya     Раздел на сайте существует: адрес из ТЗ живой либо
                       раздел нашёлся под другим именем. Текст вставляется
                       в готовую категорию, публиковать можно сразу.
  3-planovye-prochie   Раздела нет, но тема обычная: спиральные, дизельные,
                       поршневые компрессоры, сепараторы, фильтры, ресиверы.

СРЕЗЫ НЕ ПЕРЕСЕКАЮТСЯ, сумма ровно 133. Разделение по тому, ЧТО с текстом
делать: вставить в существующую категорию или сначала создать страницу.
"""
import json
import os
import re
import shutil
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from k_publikacii import DOMEN

# Темы, где сделка крупная: станция целиком, а не единица оборудования.
DOROGIE = {'mks', 'kompressornaya-stanciya',
           'azotnaya-stanciya', 'azotnaya-stanciya-modulnaya',
           'kislorodnaya-stanciya', 'kislorodnaya-stanciya-modulnaya',
           'generatory-azota', 'generatory-kisloroda'}


def tema(slug):
    return slug.split('--', 1)[1] if '--' in slug else slug


def sobrat(imya, slugi, opisanie, kuda_karta):
    papka = os.path.join(DIR, 'srezy', imya)
    shutil.rmtree(papka, ignore_errors=True)
    n = 0
    for slug in sorted(slugi):
        dom = DOMEN[slug.split('--')[0]]
        ist = os.path.join(DIR, 'k-publikacii', dom, f'{slug}.html')
        if not os.path.exists(ist):
            continue
        os.makedirs(os.path.join(papka, dom), exist_ok=True)
        shutil.copy(ist, os.path.join(papka, dom, f'{slug}.html'))
        n += 1
    # общие файлы кладём в каждый срез: без css оформления не будет
    for obshchiy in ('stili-dlya-sayta.css',):
        shutil.copy(os.path.join(DIR, obshchiy), os.path.join(papka, obshchiy))
    # meta.csv режем под состав среза
    import csv
    for dom in os.listdir(papka):
        d = os.path.join(papka, dom)
        if not os.path.isdir(d):
            continue
        ish = os.path.join(DIR, 'k-publikacii', dom, 'meta.csv')
        if not os.path.exists(ish):
            continue
        est = {f for f in os.listdir(d)}
        with open(ish, encoding='utf-8-sig') as f:
            r = list(csv.DictReader(f, delimiter=';'))
        nash = [x for x in r if x.get('Файл') in est]
        if nash:
            with open(os.path.join(d, 'meta.csv'), 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(nash[0].keys()), delimiter=';')
                w.writeheader(); w.writerows(nash)
    # карта адресатов только по своим страницам
    with open(os.path.join(papka, 'KUDA-KLAST.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Файл', 'Исход', 'Адрес из ТЗ', 'Куда класть'])
        for slug in sorted(slugi):
            z = kuda_karta.get(slug)
            if not z:
                continue
            w.writerow([f"{DOMEN[slug.split('--')[0]]}/{slug}.html", z['ishod'],
                        z.get('url_tz', ''), z['kuda'] or '(создать страницу)'])
    open(os.path.join(papka, 'ЧИТАТЬ.md'), 'w', encoding='utf-8').write(opisanie)
    arh = os.path.join(DIR, f'{imya}.zip')
    if os.path.exists(arh):
        os.remove(arh)
    subprocess.run(['zip', '-qr', arh, '.'], cwd=papka, check=True)
    return n, arh


def main():
    kuda = {z['slug']: z for z in json.load(
        open(os.path.join(DIR, 'kuda-lozhitsya.json'), encoding='utf-8'))}
    celi = {z['slug']: z for z in json.load(
        open(os.path.join(DIR, 'celi-proverka.json'), encoding='utf-8'))}
    for s, z in kuda.items():
        z['url_tz'] = celi.get(s, {}).get('url', '')

    # СРЕЗЫ НЕ ПЕРЕСЕКАЮТСЯ. Сначала я сделал «дорогие» поверх двух других,
    # и они наложились: 51 дорогая страница попала и в первый срез, и в
    # третий. Владелец просил разделение, а не три взгляда на одно и то же -
    # «надо разделение между категориями и статьями, поэтому и просил
    # 3 архива». Теперь сумма трёх равна 133 ровно.
    vse = set(kuda)
    est_kat = {s for s in vse if kuda[s]['ishod'] in ('ЕСТЬ', 'ДРУГОЙ')}
    net_kat = {s for s in vse if kuda[s]['ishod'] == 'НЕТ'}
    dorogie = {s for s in net_kat if tema(s) in DOROGIE}
    net_kat = net_kat - dorogie

    obshchee = """
Оформление берётся из `stili-dlya-sayta.css` - положите его один раз
на каждый сайт, в пользовательский CSS темы. Без него призывы лягут
обычным текстом, а широкие таблицы утащат страницу вбок на телефоне.

Адрес каждой страницы - в `KUDA-KLAST.csv`. Адреса из ТЗ плановые,
на живых сайтах существует меньше четверти: сверяйтесь с колонкой
«Куда класть», а не с колонкой «Адрес из ТЗ».
"""
    srezy = [
        ('1-dorogie-planovye', dorogie,
         f"""# Дорогие плановые: {len(dorogie)} страниц

МКС, компрессорные станции, азотные и кислородные станции и генераторы -
и все они требуют СОЗДАТЬ раздел: на сайтах таких категорий нет.

Это самый ценный срез по деньгам и самый дорогой по работе: каждая
страница означает новую категорию каталога, а не вставку текста
в существующую.
{obshchee}"""),
        ('2-est-kategoriya', est_kat,
         f"""# Тексты для СУЩЕСТВУЮЩИХ категорий: {len(est_kat)} страниц

Публиковать можно сразу. У части адрес из ТЗ живой (исход ЕСТЬ),
у части раздел нашёлся под другим именем (исход ДРУГОЙ) - например,
осушители remeza живут по адресу /catalog/ochistka-szhatogo-vozdukha/,
а азотная станция enger - по /catalog/azotnye-ustanovki/.

Класть надо по колонке «Куда класть».
{obshchee}"""),
        ('3-planovye-prochie', net_kat,
         f"""# Прочие плановые: {len(net_kat)} страниц

Раздела на сайте нет, но тема обычная, не станционная: спиральные,
дизельные и поршневые компрессоры, сепараторы, фильтры, ресиверы.
Сделка меньше, чем у станций, поэтому и очередь на создание страниц
у них ниже.

Дорогие плановые лежат в первом архиве.
{obshchee}"""),
    ]
    for imya, slugi, opis in srezy:
        n, arh = sobrat(imya, slugi, opis, kuda)
        print(f'{imya:22} страниц {n:4}  {os.path.basename(arh)}')
    print(f'\nсумма трёх: {len(dorogie) + len(est_kat) + len(net_kat)} из {len(vse)}, '
          f'пересечений {len(dorogie & est_kat) + len(dorogie & net_kat) + len(est_kat & net_kat)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
