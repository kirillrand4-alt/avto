# -*- coding: utf-8 -*-
"""Замер: на КАКИЕ документы ЕИС отвечает отказом, а какие отдаёт.

Зачем. Вторая сессия записала вывод: «ЕИС отдаёт не то, что нужно — отдаются протоколы и
разъяснения, а отказ приходит ровно на документацию о закупке, проект договора и руководство по
эксплуатации». Вывод сильный и меняет всю затею, поэтому его надо проверить на файлах, а не
принять на слово. Заодно надо назвать, чем отказ является: хранилище отвечает JSON-ом
`{"message":"Ошибка доступа. Файл с uri FZ223/… не опубликован","status":"ERROR"}` на 142 байта,
и прежний определитель типа считал это «иное» → текст пустой → «скан или пусто».

Имя документа берётся из тултипа рядом со ссылкой на файл (найдено в разметке страницы
документов, не угадано):
    <a href="…file.html?uid=…" data-tooltip='<span …>Документация компр.конденс.блок.doc</span>'>

Соответствие «файл на диске → имя документа» строится тем же порядком, каким качал
`shag_fajly`: `dict.fromkeys(...)` по странице, номер в имени `eis_f_<закупка>_<j>.bin` — это
порядковый номер ссылки на странице. Порядок повторён здесь буквально, иначе имена разъедутся с
файлами — на этом сессия уже обжигалась.

Использование:
    python3 eis_zamer_otkazov.py
"""
import collections
import glob
import os
import re
import sys

import vlozheniya as V

TULTIP = re.compile(
    r'href="(https://zakupki\.gov\.ru/223/filestore/public/1\.0/download/fz223/'
    r'file\.html\?uid=[0-9A-F]+)"[^>]*data-tooltip=\'<span[^>]*>([^<]{1,200})</span>', re.I)

# Разряды документов. Порядок важен: проверяется сверху вниз, первое совпадение выигрывает.
RAZRYADY = [
    ('техзадание', re.compile(r'техническ\w*\s*(?:задани|част)|\bТЗ\b|техзадани', re.I)),
    ('документация о закупке', re.compile(r'документаци', re.I)),
    ('проект договора/контракта', re.compile(r'договор|контракт', re.I)),
    ('руководство по эксплуатации', re.compile(r'руководств|эксплуатац|паспорт', re.I)),
    ('приложение', re.compile(r'приложени', re.I)),
    ('извещение', re.compile(r'извещени', re.I)),
    ('протокол', re.compile(r'протокол', re.I)),
    ('разъяснения', re.compile(r'разъяснени', re.I)),
    ('изменения/отмена', re.compile(r'изменени|отмен', re.I)),
    ('обоснование НМЦ', re.compile(r'обоснован|НМЦ|расчёт|расчет', re.I)),
]


def razryad(imya):
    for name, r in RAZRYADY:
        if r.search(imya):
            return name
    return 'прочее'


def main():
    # имя документа по каждому ожидаемому файлу
    imena = {}
    for p in sorted(glob.glob(os.path.join(V.DOKI, 'eis_d_*.html'))):
        n = re.search(r'eis_d_(\d+)', p).group(1)
        h = open(p, encoding='utf-8', errors='replace').read()
        # тот же порядок, что у качалки: дедуп по uid с сохранением порядка
        pary = list(dict.fromkeys(TULTIP.findall(h)))
        po_uid = {}
        for u, im in pary:
            po_uid.setdefault(u, im)
        for j, u in enumerate(dict.fromkeys(V.SSYLKA_FAJL.findall(h)), 1):
            imena[f'eis_f_{n}_{j}.bin'] = po_uid.get(u.replace('&amp;', '&'), '')

    fajly = sorted(glob.glob(os.path.join(V.FAJLY, 'eis_f_*.bin')))
    print(f'страниц документов: {len(glob.glob(os.path.join(V.DOKI, "eis_d_*.html")))}, '
          f'ссылок на файлы в них: {len(imena)}, файлов на диске: {len(fajly)}')
    bez_imeni = sum(1 for f in fajly if not imena.get(os.path.basename(f)))
    print(f'файлов, для которых имя документа не нашлось: {bez_imeni}')

    tablica = collections.defaultdict(lambda: collections.Counter())
    tipy = collections.Counter()
    primery = collections.defaultdict(list)
    for p in fajly:
        b = open(p, 'rb').read(4096)
        t = V.podpis(b, p)
        tipy[t] += 1
        im = imena.get(os.path.basename(p), '')
        r = razryad(im) if im else 'имя неизвестно'
        tablica[r]['отказ' if t == 'отказ' else 'отдан'] += 1
        if t == 'отказ' and len(primery[r]) < 2:
            primery[r].append(im)

    print('\n=== ТИПЫ ФАЙЛОВ ===')
    for k, v in tipy.most_common():
        print(f'  {v:>4}  {k}')

    print('\n=== ОТКАЗ ПО РАЗРЯДУ ДОКУМЕНТА ===')
    print(f'  {"разряд":32} {"отдан":>6} {"отказ":>6} {"доля отказа":>12}')
    for r in sorted(tablica, key=lambda x: -(tablica[x]['отказ'] + tablica[x]['отдан'])):
        c = tablica[r]
        vsego = c['отказ'] + c['отдан']
        print(f'  {r:32} {c["отдан"]:>6} {c["отказ"]:>6} {c["отказ"] / vsego:>11.0%}')
    print(f'  {"ИТОГО":32} {sum(c["отдан"] for c in tablica.values()):>6} '
          f'{sum(c["отказ"] for c in tablica.values()):>6}')

    print('\nпримеры отказов по разрядам:')
    for r, lst in primery.items():
        for im in lst:
            print(f'   {r:28} | {im[:70]}')


if __name__ == '__main__':
    main()
