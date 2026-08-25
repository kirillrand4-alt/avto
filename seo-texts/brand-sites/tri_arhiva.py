#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Три среза пакета под разные решения владельца.

    python3 tri_arhiva.py

  1-dorogie            МКС, компрессорные, азотные, кислородные станции.
                       Срез по ЦЕНЕ СДЕЛКИ, а не по готовности площадки:
                       сюда попадают и те, чья категория есть, и те, чью
                       придётся создавать.
  2-est-kategoriya     Раздел на сайте существует - адрес из ТЗ живой либо
                       раздел нашёлся под другим именем. Публиковать можно
                       сразу, разве что поправить адрес по KUDA-KLAST.csv.
  3-nuzhna-kategoriya  Подходящего раздела на сайте нет. Прежде чем класть
                       текст, страницу надо создать.

СРЕЗЫ ПЕРЕСЕКАЮТСЯ, и это не ошибка: первый режет по деньгам, второй
и третий - по готовности площадки. Дорогая статья про кислородную станцию
почти всегда лежит и в первом, и в третьем.
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

    vse = set(kuda)
    dorogie = {s for s in vse if tema(s) in DOROGIE}
    est_kat = {s for s in vse if kuda[s]['ishod'] in ('ЕСТЬ', 'ДРУГОЙ')}
    net_kat = {s for s in vse if kuda[s]['ishod'] == 'НЕТ'}

    obshchee = """
Оформление берётся из `stili-dlya-sayta.css` - положите его один раз
на каждый сайт, в пользовательский CSS темы. Без него призывы лягут
обычным текстом, а широкие таблицы утащат страницу вбок на телефоне.

Адрес каждой страницы - в `KUDA-KLAST.csv`. Адреса из ТЗ плановые,
на живых сайтах существует меньше четверти: сверяйтесь с колонкой
«Куда класть», а не с колонкой «Адрес из ТЗ».
"""
    srezy = [
        ('1-dorogie', dorogie,
         f"""# Дорогие темы: {len(dorogie)} страниц

МКС, компрессорные станции, азотные и кислородные станции и генераторы.
Срез по ЦЕНЕ СДЕЛКИ, а не по готовности площадки, поэтому он пересекается
с двумя другими: часть этих страниц ложится на существующие разделы,
часть требует создать раздел. Смотрите колонку «Исход» в KUDA-KLAST.csv.
{obshchee}"""),
        ('2-est-kategoriya', est_kat,
         f"""# Раздел на сайте есть: {len(est_kat)} страниц

Публиковать можно сразу. У части адрес из ТЗ живой (исход ЕСТЬ),
у части раздел нашёлся под другим именем (исход ДРУГОЙ) - например,
осушители remeza живут по адресу /catalog/ochistka-szhatogo-vozdukha/,
а азотная станция enger - по /catalog/azotnye-ustanovki/.

Класть надо по колонке «Куда класть».
{obshchee}"""),
        ('3-nuzhna-kategoriya', net_kat,
         f"""# Раздела на сайте нет: {len(net_kat)} страниц

Подходящего раздела каталога на сайте не нашлось - страницу придётся
создавать под текст. Это почти целиком газовое направление: кислородные
и азотные станции, компрессорные станции, МКС.

До создания страниц эти тексты публиковать некуда.
{obshchee}"""),
    ]
    for imya, slugi, opis in srezy:
        n, arh = sobrat(imya, slugi, opis, kuda)
        print(f'{imya:22} страниц {n:4}  {os.path.basename(arh)}')
    print(f'\nпересечение дорогих с «нет раздела»: {len(dorogie & net_kat)}')
    print(f'пересечение дорогих с «раздел есть»: {len(dorogie & est_kat)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
