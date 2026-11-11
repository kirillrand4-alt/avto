# -*- coding: utf-8 -*-
"""Промежуточная выгрузка готовых карточек судьи ca_boli (с проверкой поиском) -> дроп CA-BOLI-chast.md."""
import io, json, os, shutil, sys
sys.path.insert(0, r'C:\sender\server')
import ca_cel
по = {}
ист = {}
for s in io.open(r'C:\sender\server\ca\ca-boli.jsonl', encoding='utf-8', errors='replace'):
    з = json.loads(s)
    if з['роль'] == 'суд' and з.get('текст') and з.get('пров_был'):
        по[з['кат']] = з['текст']
    if з['роль'] == 'пров' and з.get('текст'):
        ист[з['кат']] = з.get('источники') or []
стр = ['# Боли и проверка физики (промежуточно: %d отраслей)' % len(по), '']
for к, т in по.items():
    г, ст, н = ca_cel.КАТ[к][:3]
    стр += ['## %s %s (%s, сейчас: %s)' % (г, н, к, ст), '', т, '', 'Источников проверки: %d' % len(ист.get(к, [])), '']
п = r'C:\sender\server\ca\CA-BOLI-chast.md'
io.open(п, 'w', encoding='utf-8').write('\n'.join(стр))
shutil.copyfile(п, r'C:\seostat\drop\drop-storage\CA-BOLI-chast.md')
print('===ИТОГ===', len(по), list(по))
