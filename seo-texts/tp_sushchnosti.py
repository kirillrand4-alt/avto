# -*- coding: utf-8 -*-
"""Раскодировать HTML-сущности в сохранённых карточках Tender.pro и пересчитать по ним поля.

Зачем. `bez_tegov` снимала разметку, но не раскодировала сущности, и `&nbsp;` внутри номера
ломал телефонную регулярку: `Тел. +7&nbsp;924&nbsp;228&nbsp;04&nbsp;44` не совпадал ни с одним
уровнем — между группами цифр разрешены пробел, скобка и дефис, а не строка `&nbsp;`.

Замер по 9 021 перевыкаченной карточке: сущности стоят в **3 020** карточках по рубежу этого
скрипта (`&имя;` и `&#число;`); по узкому перечню шести самых частых их 3 014, один `&nbsp;` —
17 128 раз. Числа названы оба, потому что рубеж разный, а не потому что замер разошёлся.
Раскодировка меняет колонку телефонов у 112 карточек и достаёт 101 номер, которого не было.

Но цену надо назвать точно, а не громко. Из этих 101 карточки **88 провайдер и так видел**: у
них был другой телефон или техническое слово, они попадали в отбор, и модель номер с `&nbsp;`
читала правильно — «Инженер-энергетик Волков Максим Валерьевич … Тел. +7 924 228 04 44»
(ТехноНИКОЛЬ) есть в старом разборе. Страдала регулярка, а не разбор.

Настоящая потеря — **13 карточек**, у которых не было ни телефона, ни технического слова, и
поэтому они были отсечены от разбора вовсе: Черкизово, Комбинат Магнезит, КАМАЗ. Их и надо
переспросить после пересчёта.

Скрипт ничего не качает: текст уже лежит в CSV. Набор колонок берётся ИЗ ЗАГОЛОВКА файла —
жёсткий список колонок в писателе и есть тот механизм, которым соседняя сессия сдвинула
значения на позицию.

Использование:
    python3 tp_sushchnosti.py [--kart ИМЯ.csv] [--suho]
"""
import csv
import html
import os
import re
import shutil
import sys

import tenderpro_harvest as T

csv.field_size_limit(10 ** 7)

BAZA = os.path.dirname(os.path.abspath(__file__))
TP = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
SUSHCH = re.compile(r'&(?:[a-zA-Z]{2,8}|#\d{2,5});')


def main():
    suho = '--suho' in sys.argv
    kart = os.path.join(TP, sys.argv[sys.argv.index('--kart') + 1]) if '--kart' in sys.argv \
        else os.path.join(TP, 'tp-kartochki-polnye.csv')
    rows = list(csv.DictReader(open(kart, encoding='utf-8-sig'), delimiter=';'))
    cols = list(rows[0].keys())


    s_sushch = sum(1 for r in rows if SUSHCH.search(r.get('comment') or ''))
    novyh_tel = novyh_teh = 0
    perespros = []
    for r in rows:
        c = r.get('comment') or ''
        if not SUSHCH.search(c):
            continue
        dec = re.sub(r'\s+', ' ', html.unescape(c)).strip()
        bylo_tel = (r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or '')
        bylo_teh = r.get('est_teh') or ''
        tel_r = r.get('telefony_razmetka') or ''
        # Дополняем, а не переписываем: колонка могла быть заполнена другим прогоном.
        staroe = [t.strip() for t in (r.get('telefony_tekst') or '').split('|') if t.strip()]
        nashli = [t for t in T.telefony_iz_teksta(dec) if t not in tel_r]
        r['comment'] = dec
        r['telefony_tekst'] = ' | '.join(dict.fromkeys(staroe + nashli))
        r['est_teh'] = '1' if T.TEH.search(dec) else bylo_teh
        r['pochty'] = ' | '.join(dict.fromkeys(
            list((r.get('pochty') or '').split(' | ') if r.get('pochty') else [])
            + T.MAIL.findall(dec)))
        if r['telefony_tekst'] != ' | '.join(staroe):
            novyh_tel += 1
        if r['est_teh'] and not bylo_teh:
            novyh_teh += 1
        # Карточка, которую прежде отсекали вовсе, а теперь есть за что спрашивать.
        if not (bylo_tel or bylo_teh) and (r['telefony_tekst'] or r['est_teh']):
            perespros.append(r['tender_id'])

    print(f'карточек: {len(rows)}, с сущностями: {s_sushch}')
    print(f'  колонка телефонов изменилась у: {novyh_tel}')
    print(f'  техническое слово появилось у:  {novyh_teh}')
    print(f'  прежде отсечённых, теперь есть что спросить: {len(perespros)}')
    if perespros:
        print('  их id: ' + ' '.join(perespros))

    if suho:
        print('сухой прогон, файл не изменён')
        return
    shutil.copy(kart, kart + '.do-sushchnostey')
    with open(kart, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    # Отчёт цифрой ИЗ ЗАПИСАННОГО ФАЙЛА: счётчик в памяти на этой задаче уже расходился с файлом.
    pr = list(csv.DictReader(open(kart, encoding='utf-8-sig'), delimiter=';'))
    print(f'записано: строк {len(pr)}, колонок {len(pr[0].keys())}, '
          f'осталось карточек с сущностями {sum(1 for r in pr if SUSHCH.search(r.get("comment") or ""))}, '
          f'с телефоном {sum(1 for r in pr if (r.get("telefony_razmetka") or r.get("telefony_tekst")))}')
    tyazh = max(pr[0].keys(), key=lambda c: sum(len(r.get(c) or '') for r in pr))
    print(f'  проверка на сдвиг колонок: самая тяжёлая колонка «{tyazh}» '
          f'({"верно" if tyazh == "comment" else "СДВИГ!"})')


if __name__ == '__main__':
    main()
