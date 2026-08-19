# -*- coding: utf-8 -*-
"""Сверка новой сборки с живой: какие русские строки пропали, какие появились."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ЖИВОЙ = r'C:\sender\web\dist\assets'
НОВЫЙ = r'C:\sender\sender\web\dist\assets'


def строки(папка):
    из = set()
    # ЖИВАЯ папка хранит ВСЕ прежние сборки — сравнивать надо только с той,
    # что реально отдаётся: её имя стоит в index.html.
    свежий = None
    инд = os.path.join(os.path.dirname(папка), 'index.html')
    if os.path.exists(инд):
        м = re.search(r'assets/(index-[\w-]+\.js)',
                      io.open(инд, encoding='utf-8', errors='replace').read())
        свежий = м.group(1) if м else None
    for f in os.listdir(папка):
        if not f.endswith('.js') or f.endswith('.map'):
            continue
        if свежий and f != свежий:
            continue
        t = io.open(os.path.join(папка, f), encoding='utf-8', errors='replace').read()
        # Ловим РУССКИЕ КУСКИ, а не строки в кавычках: минификатор волен
        # переписать кавычки, склеить или разбить литерал, и сравнение по
        # «"..."» выдаёт ложную тревогу — один раз уже напугало «пропажей»
        # подписей, которые на деле были на месте.
        for м in re.finditer(r'[А-Яа-яЁё][А-Яа-яЁё ,.:;!?()«»—-]{3,59}', t):
            s = м.group(0).strip()
            if len(s) >= 4:
                из.add(s)
    return из


ж, н = строки(ЖИВОЙ), строки(НОВЫЙ)
пропало = sorted(ж - н)
появилось = sorted(н - ж)
print(json.dumps({'в_живой': len(ж), 'в_новой': len(н),
                  'пропало_всего': len(пропало), 'пропало': пропало[:40],
                  'появилось_всего': len(появилось), 'появилось': появилось[:20]},
                 ensure_ascii=False, indent=1)[:3600])
