#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Существует ли категория, на которую ляжет статья.

    python3 proverit_celi.py [--potokov 6]

ЧЕГО НЕ ХВАТАЛО. Вся приёмка до сих пор отвечала на вопрос «как страница
выглядит». Владелец спросил другое: «лягут ли статьи на нужные категории».
Вопрос правильный и незакрытый - адрес назначения лежит в шапке каждого
ТЗ, но живым его никто не видел.

Три исхода, и они разные по смыслу:
  200          категория есть, статья ложится на существующую страницу;
  404          категории нет - её придётся СОЗДАВАТЬ, а это другая работа
               и другой разговор с владельцем;
  редирект     адрес живой, но ведёт в другое место - класть надо туда,
               куда он ведёт, иначе текст осядет на странице, с которой
               посетителя уводят.
"""
import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))


def sprosit(para):
    slug, url = para
    r = subprocess.run(
        ['curl', '-sS', '-o', '/dev/null', '--max-time', '30',
         '-w', '%{http_code} %{redirect_url}', url],
        capture_output=True, text=True)
    chasti = (r.stdout or '').strip().split(None, 1)
    kod = chasti[0] if chasti else '000'
    kuda = chasti[1] if len(chasti) > 1 else ''
    return {'slug': slug, 'url': url, 'kod': kod, 'redirect': kuda}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--potokov', type=int, default=6)
    ap.add_argument('--karta', default=os.path.join(DIR, 'celevye-url.json'))
    ap.add_argument('--out', default=os.path.join(DIR, 'celi-proverka.json'))
    a = ap.parse_args()

    karta = json.load(open(a.karta, encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=a.potokov) as p:
        itog = list(p.map(sprosit, sorted(karta.items())))
    json.dump(itog, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    schet = {}
    for z in itog:
        schet[z['kod']] = schet.get(z['kod'], 0) + 1
    print('коды ответов:', dict(sorted(schet.items())))
    for z in itog:
        if z['kod'] != '200':
            print(f"  {z['kod']}  {z['slug'][:44]:44} {z['url'][:64]}")
            if z['redirect']:
                print(f"        -> {z['redirect'][:80]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
