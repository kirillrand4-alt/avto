# -*- coding: utf-8 -*-
"""Сторож: состояние потоков и что выложено. Отвечает числами из файлов, не по памяти.

Проверяет по каждому потоку: есть ли он вообще (пусто = не стартовал, а не «медленно»),
сколько строк, сколько с ошибкой, сколько личных мобильных добыто. Записи с ошибкой
пройденными не считаются. Печатает голые числа.
"""
import collections
import glob
import io
import json
import os
import re

OPS = r'C:\sender\_ops'
POTOKI = ('p25-imena.jsonl', 'p25-obratnyy.jsonl', 'p25-dobavochnyy.jsonl',
          'p25-dobit.jsonl', 'p25-nomer.jsonl')


def cifry(s):
    c = re.sub(r'\D', '', str(s or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


def lichnyy(z):
    """Личный мобиль: любое поле-номер, начинающееся на 79, не помеченное неличным."""
    tekst = json.dumps(z, ensure_ascii=False)
    for n in re.findall(r'7\d{10}', re.sub(r'\D', ' ', tekst)):
        if n.startswith('79'):
            return True
    for k in ('phone', 'telefon', 'nomer', 'znachenie'):
        if cifry(z.get(k)).startswith('79'):
            return True
    return False


def naydi(imya):
    """Поток может лежать в _ops или рядом; ищем по имени."""
    for baza in (OPS, r'C:\sender', r'C:\seostat\data'):
        p = os.path.join(baza, imya)
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(OPS, '**', imya), recursive=True)
    return hits[0] if hits else ''


svod = {}
for imya in POTOKI:
    p = naydi(imya)
    if not p:
        svod[imya] = {'есть': False}
        print('%-24s НЕТ ФАЙЛА — не стартовал' % imya)
        continue
    strok = sboev = lichnyh = 0
    inn_vidano = set()
    posledn = ''
    for stroka in io.open(p, encoding='utf-8', errors='replace'):
        stroka = stroka.strip()
        if not stroka:
            continue
        strok += 1
        try:
            z = json.loads(stroka)
        except Exception:  # noqa: BLE001
            sboev += 1
            continue
        if z.get('error') or z.get('oshibka') or z.get('status') == 'error':
            sboev += 1
            continue
        if lichnyy(z):
            lichnyh += 1
        for k in ('inn', 'ИНН'):
            if z.get(k):
                inn_vidano.add(str(z[k]))
        posledn = stroka[:70]
    mtime = int(os.path.getmtime(p))
    svod[imya] = {'есть': True, 'строк': strok, 'сбоев': sboev,
                  'личных_мобильных': lichnyh, 'разных_инн': len(inn_vidano),
                  'mtime': mtime}
    print('%-24s строк %-6d сбоев %-5d личных79 %-5d разныхИНН %-5d'
          % (imya, strok, sboev, lichnyh, len(inn_vidano)))

print('ИТОГ ' + json.dumps(svod, ensure_ascii=False))
