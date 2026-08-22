#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Качество анкоров - только на статьях, НАЧАТЫХ после правки промпта.

    python3 zamer_ankorov.py [файл-с-правкой]

ЗАЧЕМ ОТДЕЛЬНЫЙ СЧЁТЧИК. Дважды за ночь я мерил последствия правки
по времени ИЗМЕНЕНИЯ файла статьи и дважды получал чепуху: статья
пишется пять-одиннадцать минут, подпроцесс читает код при запуске,
и статья, законченная через две минуты после правки, шла ещё
по старому промпту. Так я едва не отчитался о падении качества
анкоров с 29% до 83%, хотя ни одна из «новых» статей новый промпт
не видела.

Время начала считается точно: mtime минус sekund из меты. Статьи,
начатые раньше правки, в замер не берутся вовсе - не «взвешиваются
с оговоркой», а именно не берутся, потому что оговорку в отчёте
легко потерять.
"""
import glob
import html as H
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))

# Анкор слабый, если он не называет предмет: одно слово (обычно падежный
# обрывок - «фильтров», «осушителем») либо глагольная форма («подключены»).
GLAGOL = re.compile(r'\b\w+(?:ены|ена|ено|ется|ются|лся|лись|ать|ить)\b', re.I)
SSYLKA = re.compile(r'<a[^>]+href="([^"#][^"]*)"[^>]*>(.*?)</a>', re.S | re.I)


def _tekst(kus):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', '', kus))).strip()


def nachalo(put):
    """Когда статью НАЧАЛИ писать: время файла минус длительность."""
    meta = put[:-5] + '.meta.json'
    dlit = 0
    if os.path.exists(meta):
        try:
            dlit = json.load(open(meta, encoding='utf-8')).get('sekund') or 0
        except Exception:
            dlit = 0
    return os.path.getmtime(put) - dlit


def slabyy(ankor):
    if GLAGOL.search(ankor):
        return 'глагольная форма'
    if len(ankor.split()) == 1:
        return 'одно слово'
    return ''


def main():
    # РУБЕЖ ЗАДАЁТСЯ ЯВНО, А НЕ ВРЕМЕНЕМ ФАЙЛА. Первая версия брала
    # mtime gen_statya.py - и обнулила замер, как только я тронула тот же
    # файл ради другой починки (список форм FAQ). Рубеж должен указывать
    # на СОБЫТИЕ, за которым следят, а не на файл, который правят по
    # десять раз за ночь.
    RUBEZH_ANKOROV = '2026-08-22 19:31:39'   # усиление промпта про анкоры
    zadan = sys.argv[1] if len(sys.argv) > 1 else RUBEZH_ANKOROV
    if os.path.exists(zadan):
        rubezh, pravka = os.path.getmtime(zadan), zadan
    else:
        import datetime
        rubezh = datetime.datetime.strptime(zadan, '%Y-%m-%d %H:%M:%S').timestamp()
        pravka = f'рубеж {zadan}'
    vsego = slab = statey = 0
    plohie = []
    for f in sorted(glob.glob(os.path.join(DIR, 'statyi', '*.html'))):
        if '.brak' in f or nachalo(f) < rubezh:
            continue
        statey += 1
        t = open(f, encoding='utf-8').read()
        for m in SSYLKA.finditer(t):
            a = _tekst(m.group(2))
            if not a:
                continue
            vsego += 1
            p = slabyy(a)
            if p:
                slab += 1
                plohie.append((os.path.basename(f)[:40], a, p))
    import time as _t
    print(f'рубеж: {_t.strftime("%H:%M:%S", _t.localtime(rubezh))} ({os.path.basename(pravka)})')
    print(f'статей, НАЧАТЫХ после правки: {statey}')
    if not vsego:
        print('ссылок в них пока нет - рано судить')
        return 0
    print(f'анкоров {vsego}, слабых {slab} ({slab / vsego:.0%})')
    for f, a, p in plohie:
        print(f'   {f:40} «{a[:40]}»  {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
