# -*- coding: utf-8 -*-
"""Скопировать боевые исходники панели обзвона на дроп для скачивания."""
import json
import os
import shutil

SRC = r'C:\seostat\app'
DST = r'C:\seostat\drop\drop-storage'

FILES = [
    ('api\\routes_obzvon.py', 'obz__routes_obzvon.py'),
    ('services\\callbase.py', 'obz__callbase.py'),
    ('db\\models.py', 'obz__models.py'),
    ('templates\\obzvon.html', 'obz__obzvon.html'),
    ('templates\\obzvon_card.html', 'obz__obzvon_card.html'),
    ('templates\\obzvon_list.html', 'obz__obzvon_list.html'),
    ('templates\\obzvon_base.html', 'obz__obzvon_base.html'),
    ('templates\\base.html', 'obz__base.html'),
    ('static\\css\\app.css', 'obz__app.css'),
    ('main.py', 'obz__main.py'),
    ('obzvon.py', 'obz__obzvon_mod.py'),
]


def main():
    out = {'скопировано': [], 'нет': []}
    for rel, dst_name in FILES:
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            out['нет'].append(rel)
            continue
        shutil.copy(src, os.path.join(DST, dst_name))
        out['скопировано'].append(f'{rel} -> {dst_name} ({os.path.getsize(src)}b)')
    # заодно список шаблонов и статики целиком
    for d in ('templates', 'static\\css', 'static\\js'):
        p = os.path.join(SRC, d)
        if os.path.isdir(p):
            out[d] = sorted(os.listdir(p))[:30]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
