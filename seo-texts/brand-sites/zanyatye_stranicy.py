#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Столкновения адресов и страницы, где текст уже стоит.

    python3 zanyatye_stranicy.py

ДВЕ БЕДЫ, НАЙДЕННЫЕ ПОСЛЕ СБОРКИ СРЕЗОВ.

1. СТОЛКНОВЕНИЯ. Сопоставитель ловил раздел по слову темы, и слово «азот»
   одинаково подходило трём разным статьям: «азотная станция», «модульная
   азотная станция», «генераторы азота». Все три уехали на один адрес
   /catalog/azotnye-ustanovki/. Одна страница - один текст, значит двое
   лишние: им нужна своя страница, а не чужая.

   Побеждает БАЗОВАЯ тема - без «модульная» и без «генераторы»: модульная
   станция и генератор это отдельные товары, а не другое название той же
   категории.

2. ЗАНЯТЫЕ СТРАНИЦЫ. У enger на азотных и кислородных установках, на
   центробежных и винтовых компрессорах SEO-текст УЖЕ СТОИТ - от двух
   с половиной до семи тысяч знаков. Класть туда наш текст значит
   переписывать чужую работу, а владелец этого не просил.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

# Сколько знаков в блоке считаем «текст уже стоит». Ниже порога - это
# короткое описание категории, а не статья.
PORT_ZANYATO = 1500


def bazovaya(tema):
    """Базовая ли тема - та, что и должна занять существующий раздел."""
    return not (tema.endswith('-modulnaya') or tema.startswith('generatory-'))


def tema(slug):
    return slug.split('--', 1)[1] if '--' in slug else slug


def skolko_teksta(url):
    """Сколько на странице СВЯЗНОЙ ПРОЗЫ, а не всего текста.

    Три подхода не сработали, прежде чем получился этот.

    Первый брал самый крупный div с тремя абзацами - и на половине сайтов
    захватывал всю страницу с меню, карточками и подвалом: у zif вышло
    15 тысяч знаков там, где статьи нет вовсе.

    Второй считал длинные абзацы - и дал 396 тысяч знаков на странице
    категории enger. Причина оказалась не в шаблоне: на той странице
    один <p> просто НЕ ЗАКРЫТ, и «абзац» вобрал в себя всё меню с
    каталогом. Разметка чужая, чинить её не наше дело, но и мерить
    по ней нельзя.

    Отсюда правило: отсечь служебные блоки до замера и поставить потолок
    на длину абзаца. Настоящий абзац живёт между двумя сотнями и двумя
    тысячами знаков; всё, что длиннее, - склейка из-за незакрытого тега.
    """
    if not url:
        return 0
    r = subprocess.run(['curl', '-sS', '-L', '--max-time', '30', url],
                       capture_output=True, text=True)
    h = r.stdout or ''
    for teg in ('script', 'style', 'nav', 'header', 'footer', 'aside'):
        h = re.sub(r'<' + teg + r'\b.*?</' + teg + r'>', ' ', h, flags=re.S | re.I)
    dlinnye = 0
    for m in re.finditer(r'<p[^>]*>((?:(?!</p>).)*)</p>', h, re.S | re.I):
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()
        if 200 <= len(t) <= 2000:
            dlinnye += len(t)
    return dlinnye


def main():
    kuda = {z['slug']: z for z in json.load(
        open(os.path.join(DIR, 'kuda-lozhitsya.json'), encoding='utf-8'))}
    celi = {z['slug']: z for z in json.load(
        open(os.path.join(DIR, 'celi-proverka.json'), encoding='utf-8'))}

    # 1. Разводим столкновения
    po_adresu = {}
    for s, z in kuda.items():
        u = z['kuda'] or celi[s]['url']
        if z['ishod'] in ('ЕСТЬ', 'ДРУГОЙ'):
            po_adresu.setdefault(u, []).append(s)
    razvedeno = 0
    for u, spisok in po_adresu.items():
        if len(spisok) < 2:
            continue
        bazovye = [s for s in spisok if bazovaya(tema(s))]
        pobeditel = sorted(bazovye)[0] if bazovye else sorted(spisok)[0]
        for s in spisok:
            if s != pobeditel:
                kuda[s]['ishod'] = 'НЕТ'
                kuda[s]['kuda'] = ''
                kuda[s]['pochemu'] = f'адрес занят страницей {pobeditel}'
                razvedeno += 1
    print(f'разведено столкновений: {razvedeno}')

    # 2. Смотрим, где текст уже стоит
    proverit = [(s, z['kuda'] or celi[s]['url'])
                for s, z in kuda.items() if z['ishod'] in ('ЕСТЬ', 'ДРУГОЙ')]
    with ThreadPoolExecutor(max_workers=6) as p:
        dliny = list(p.map(lambda x: (x[0], x[1], skolko_teksta(x[1])), proverit))
    # Старую пометку снимаем ДО новой: замер переписывался трижды, и
    # значения от прежних, ошибочных версий оставались в json. Из-за них
    # enger--kompressornaya-stanciya попала в исключённые, хотя по верному
    # замеру текста на её странице нет.
    for z in kuda.values():
        z.pop('zanyato', None)
    zanyato = [(s, u, n) for s, u, n in dliny if n >= PORT_ZANYATO]
    for s, u, n in zanyato:
        kuda[s]['zanyato'] = n
    print(f'\nстраниц, где текст УЖЕ СТОИТ (от {PORT_ZANYATO} знаков): {len(zanyato)}')
    for s, u, n in sorted(zanyato, key=lambda x: -x[2]):
        print(f'   {s[:44]:44} {n:6} знаков  {u[:52]}')

    json.dump(list(kuda.values()),
              open(os.path.join(DIR, 'kuda-lozhitsya.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
