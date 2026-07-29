# -*- coding: utf-8 -*-
"""Дельта реестра ЭПБ: какие заключения появились со времени прошлой выгрузки.

Зачем. Всё, что мы собрали, описывает прошлое: машина отработала срок, экспертиза уже
сделана. Дельта — единственный способ превратить реестр в **сигнал настоящего времени**:
новое заключение означает, что машину только что обследовали и решение по ней принимается
сейчас, а не когда-нибудь.

Как считать. Ключ — номер заключения (`nomer`), он уникален и не меняется. Дельта — это
номера, которых не было в базовом слепке. Дата заключения для этого не годится: заключение
попадает в реестр с задержкой, и «свежая дата» не то же самое, что «новая запись».

Использование:
    # заложить базу (один раз по имеющимся выгрузкам)
    python3 mpb_delta.py baza engineers-lens/centro/epb-centro-vse.csv [ещё файлы...]
    # посчитать дельту после новой выгрузки
    python3 mpb_delta.py delta <новая-выгрузка.csv> [--obnovit]

Файл слепка: engineers-lens/centro/delta-baza.json — только номера и дата закладки,
без персональных данных.
"""
import csv
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
BAZA = os.path.join(DIR, 'engineers-lens', 'centro', 'delta-baza.json')


def nomera(path):
    out = {}
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            n = (r.get('nomer') or '').strip()
            if n:
                out[n] = r
    return out


def zaloz(paths, data_zakladki):
    vse = {}
    for p in paths:
        got = nomera(p)
        print(f'  {os.path.basename(p)}: {len(got)} заключений', file=sys.stderr)
        vse.update(got)
    json.dump({'zalozheno': data_zakladki, 'nomera': sorted(vse)},
              open(BAZA, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'база заложена: {len(vse)} номеров → {BAZA}', file=sys.stderr)


def delta(path, obnovit):
    if not os.path.exists(BAZA):
        sys.exit('базы нет, сначала: mpb_delta.py baza <файлы...>')
    b = json.load(open(BAZA, encoding='utf-8'))
    staryе = set(b['nomera'])
    novye_vse = nomera(path)
    novye = {n: r for n, r in novye_vse.items() if n not in staryе}
    print(f'база от {b["zalozheno"]}: {len(staryе)} номеров', file=sys.stderr)
    print(f'в выгрузке: {len(novye_vse)}, из них НОВЫХ: {len(novye)}', file=sys.stderr)
    if novye:
        out = path.replace('.csv', '-delta.csv')
        cols = list(next(iter(novye.values())).keys())
        with open(out, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
            w.writeheader()
            w.writerows(novye.values())
        print(f'дельта записана → {out}', file=sys.stderr)
        # чем свежая дельта интересна: отрицательные выводы и истекающие сроки
        plohie = [r for r in novye.values() if 'не ' in (r.get('vyvod') or '')]
        print(f'  из них с выводом «не соответствует» или «не в полной мере»: {len(plohie)}',
              file=sys.stderr)
        for r in list(novye.values())[:8]:
            print(f"    {r.get('data','')}  {r.get('zakazchik','')[:34]:<34} "
                  f"{(r.get('obekt') or '')[:52]}", file=sys.stderr)
    if obnovit:
        b['nomera'] = sorted(staryе | set(novye_vse))
        json.dump(b, open(BAZA, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'база обновлена: {len(b["nomera"])} номеров', file=sys.stderr)


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: mpb_delta.py baza <файлы...> | mpb_delta.py delta <файл> [--obnovit]')
    rezhim = sys.argv[1]
    if rezhim == 'baza':
        # дату закладки передаём снаружи: в скриптах этой сессии время берётся из данных,
        # а не из системных часов, чтобы повторный прогон давал тот же результат
        data = os.environ.get('DATA_ZAKLADKI', 'не указана')
        zaloz(sys.argv[2:], data)
    elif rezhim == 'delta':
        delta(sys.argv[2], '--obnovit' in sys.argv)
    else:
        sys.exit('режим: baza | delta')


if __name__ == '__main__':
    main()
