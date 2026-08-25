#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Настоящие категории каталога каждого сайта - с живых страниц.

    python3 sobrat_kategorii.py

ЗАЧЕМ. Адрес в шапке ТЗ оказался ПЛАНОВЫМ, а не существующим: из 133
целевых страниц живы 28, остальные 105 отдают 404. У kraftmann слуги
случайно совпали с настоящими (11 из 11), у remeza не совпал ни один -
там категории зовутся generatori-azota, ochistka-szhatogo-vozdukha,
modulnye-kompressornye-stantsii.

То есть статьи писались под придуманные адреса. Прежде чем решать,
создавать эти страницы или класть тексты на существующие, надо знать,
какие категории на сайтах ЕСТЬ. Это и собираем - с живых страниц,
а не из головы.
"""
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
SAYTY = ['abac-kompressor.ru', 'ac-kompressor.ru', 'berg-kompressor.ru',
         'crossair-compressor.ru', 'dali-kompressor.ru', 'ekomak-kompressor.com',
         'enger-air.ru', 'fini-compressor.com', 'ironmac-compressor.com',
         'kraftmann-kompressor.com', 'remeza-kompressor.ru', 'zif-kompressor.ru']


def kategorii(dom):
    """Разделы каталога с их H1 - имя важнее адреса при сопоставлении."""
    r = subprocess.run(['curl', '-sS', '-L', '--max-time', '35',
                        f'https://{dom}/catalog/'], capture_output=True, text=True)
    h = r.stdout or ''
    puti = sorted(set(re.findall(r'href="(/catalog/[a-z0-9][a-z0-9/_-]*/)"', h)))
    # Имя раздела берём из текста ссылки на него: подпись человеку понятнее
    # адреса и переживает переименование слуга.
    imena = {}
    for m in re.finditer(r'href="(/catalog/[a-z0-9][a-z0-9/_-]*/)"[^>]*>\s*([^<]{3,80}?)\s*<', h):
        put, imya = m.group(1), ' '.join(m.group(2).split())
        if imya and put not in imena:
            imena[put] = imya
    return {'domen': dom, 'puti': puti,
            'imena': {p: imena.get(p, '') for p in puti}}


def main():
    with ThreadPoolExecutor(max_workers=6) as p:
        itog = list(p.map(kategorii, SAYTY))
    json.dump({z['domen']: z for z in itog},
              open(os.path.join(DIR, 'kategorii-saytov.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    for z in itog:
        print(f"{z['domen']:26} разделов {len(z['puti'])}")
        for p_ in z['puti'][:4]:
            print(f"     {p_:44} {z['imena'].get(p_, '')[:44]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
