# -*- coding: utf-8 -*-
"""Где живёт код рассыльщика, который принимает привязку «ядро».

Третья сессия назвала файл newsco_op.py и строку 480. У меня в репозитории
такого имени нет — есть news_from_company.py. Прежде чем править, надо
убедиться, что правлю ТОТ файл, который делает кампанию: правка не в том
месте выглядит как сделанная работа и ничего не меняет.
"""
import glob
import os
import re

КОРНИ = (r'C:\sender\server', r'C:\seostat', r'C:\sender')


def main():
    найдено = []
    for корень in КОРНИ:
        for п in glob.glob(os.path.join(корень, '**', '*.py'), recursive=True):
            if '__pycache__' in п:
                continue
            имя = os.path.basename(п).lower()
            if 'newsco' in имя or 'news_from_company' in имя or 'campaign' in имя:
                найдено.append(п)
    for п in sorted(set(найдено)):
        print(f'{os.path.getsize(п):>8}  {п}')
        try:
            текст = open(п, encoding='utf-8', errors='replace').read()
        except Exception:  # noqa: BLE001
            continue
        for m in re.finditer(r"^.*'ядро'.*$", текст, re.M):
            n = текст[:m.start()].count('\n') + 1
            print(f'      строка {n}: {m.group(0).strip()[:110]}')
    print()
    # где лежит сам файл кампании
    for корень in (r'C:\seostat\drop\drop-storage', r'C:\sender\server'):
        for п in glob.glob(os.path.join(корень, '*campaign*')):
            print(f'файл кампании: {os.path.getsize(п):>9}  {п}')


if __name__ == '__main__':
    main()
