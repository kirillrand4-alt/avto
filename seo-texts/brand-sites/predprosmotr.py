#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Предпросмотр публикации: статья в родном CSS сайта.

    python3 predprosmotr.py [--css <папка со скачанным css>] [--out predprosmotr]

Не пакет к публикации, а проверка ПЕРЕД ним: как страница ляжет, если
вставить её в сайт как есть. Берём настоящие таблицы стилей сайта
(внешние скачаны, инлайновые вырезаны из выгрузки), добавляем наш
stili-dlya-sayta.css и кладём тело в тот контейнер, что у сайта.
"""
import argparse
import glob
import hashlib
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))

# Контейнер SEO-текста и класс темы на body - из выгрузки живых страниц.
KONTEYNER = {
    'enger-air.ru': ('article col-md-12 mb-4', ''),
    # НЕ «text hidden-xs»: этот класс я вписал сам, и он оказался ловушкой -
    # hidden-xs в бутстрапе ПРЯЧЕТ блок на телефонах, и все три мобильных
    # снимка berg вышли пустыми. Настоящий контейнер SEO-текста на живой
    # странице - item-desc, в нём 18 абзацев.
    'berg-kompressor.ru': ('item-desc', ''),
    'ironmac-compressor.com': ('row mb-4', 'bx-theme-green'),
    'dali-kompressor.ru': ('catalog-footer-seo', 'bx-theme-blue'),
    'crossair-compressor.ru': ('row bx-blue', 'bx-theme-blue'),
    'fini-compressor.com': ('bx-section-desc', 'bx-theme-red'),
    'abac-kompressor.ru': ('text', 'bx-theme-yellow'),
    'ac-kompressor.ru': ('text', 'bx-theme-green'),
    'ekomak-kompressor.com': ('text', ''),
    'kraftmann-kompressor.com': ('text', ''),
    'remeza-kompressor.ru': ('text', ''),
    'zif-kompressor.ru': ('text', 'bx-theme-red'),
}


def stili_sayta(dom, papka_css):
    """Скачанный css ВШИВАЕТСЯ в страницу, инлайновые стили следом.

    СНАЧАЛА ЗДЕСЬ СТОЯЛИ ССЫЛКИ <link href="https://сайт/...css">, И ЭТО
    БЫЛО МОЕЙ ОШИБКОЙ. У браузера, открывающего страницу по file://, сети
    нет: все одиннадцать таблиц стилей молча не загрузились, страница
    отрисовалась голым HTML - Times New Roman, синие подчёркнутые ссылки,
    таблицы без рамок, кнопки без фона.

    Хуже всего, что предпросмотр при этом ВЫГЛЯДЕЛ работающим, и осмотр
    по таким снимкам дал длинный список «дефектов вёрстки», которых
    в статьях нет: их source был в неподключённом CSS.

    Поэтому файл читается с диска и вставляется телом. Картинки и шрифты
    внутри url() всё равно не подтянутся - для проверки раскладки, цветов
    и кнопок это неважно.
    """
    kuski = []
    syroy = os.path.join(DIR, 'sayty-syrye', f'{dom}.html')
    h = open(syroy, encoding='utf-8', errors='replace').read() if os.path.exists(syroy) else ''
    for u in re.findall(r'<link[^>]+href="([^"]+\.css[^"]*)"', h, re.I):
        polnyy = u if u.startswith('http') else f'https://{dom}{u if u.startswith("/") else "/" + u}'
        imya = hashlib.md5(polnyy.encode()).hexdigest()[:10] + '.css'
        put = os.path.join(papka_css, dom, imya)
        if os.path.exists(put):
            telo = open(put, encoding='utf-8', errors='replace').read()
            kuski.append(f'<style>/* {os.path.basename(u)[:60]} */\n{telo}</style>')
    for st in re.findall(r'<style[^>]*>(.*?)</style>', h, re.S | re.I):
        if st.strip():
            kuski.append(f'<style>{st}</style>')
    return '\n'.join(kuski)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--css', default=os.path.join(DIR, 'css-saytov'))
    ap.add_argument('--out', default=os.path.join(DIR, 'predprosmotr'))
    ap.add_argument('--iz', default='k-publikacii')
    ap.add_argument('--po-odnoy', action='store_true',
                    help='по одной странице с сайта, а не все')
    a = ap.parse_args()

    nash = open(os.path.join(DIR, 'stili-dlya-sayta.css'), encoding='utf-8').read()
    sdelano = 0
    for dom in sorted(KONTEYNER):
        fajly = sorted(glob.glob(os.path.join(DIR, a.iz, dom, '*.html')))
        if a.po_odnoy:
            fajly = fajly[:1]
        klass, tema = KONTEYNER[dom]
        shapka = stili_sayta(dom, a.css)
        papka = os.path.join(a.out, dom)
        os.makedirs(papka, exist_ok=True)
        for f in fajly:
            telo = open(f, encoding='utf-8').read()
            slug = os.path.basename(f)[:-5]
            stranica = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{slug}</title>
{shapka}
<style>{nash}</style>
</head>
<body class="{tema}">
<div class="container">
  <h1>{slug}</h1>
  <div class="{klass}">
{telo}
  </div>
</div>
</body></html>'''
            open(os.path.join(papka, f'{slug}.html'), 'w', encoding='utf-8').write(stranica)
            sdelano += 1
        print(f'{dom:26} {len(fajly):3} стр., контейнер .{klass}')
    print(f'всего страниц предпросмотра: {sdelano}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
