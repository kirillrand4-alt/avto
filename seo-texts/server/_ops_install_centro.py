# -*- coding: utf-8 -*-
"""Установка панели «Центробежные 1/2» в приложение обзвона (C:\\seostat\\app).

Почему отдельный шаг: panel_file_put пишет только под C:\\sender, а панель
обзвона живёт в C:\\seostat\\app. Поэтому файлы сперва кладутся в
C:\\sender\\_ops\\centro\\, а этот скрипт разносит их по местам — с бэкапом.

Путь подключения роутера НЕ угадываем: ищем в obzvon.py существующую регистрацию
router обзвона и вставляем свою рядом. Если не нашли — честно отказываемся, а не
портим файл вслепую.

Запуск: python _ops_install_centro.py [apply]
"""
import json
import os
import re
import shutil
import sys
import time

SRC = r'C:\sender\_ops\centro'
APP = r'C:\seostat\app'

FILES = [
    ('routes_centro.py', os.path.join(APP, 'api', 'routes_centro.py')),
    ('centro.html', os.path.join(APP, 'templates', 'centro.html')),
    ('centro_card.html', os.path.join(APP, 'templates', 'centro_card.html')),
    ('centro_list.html', os.path.join(APP, 'templates', 'centro_list.html')),
    ('centro.css', os.path.join(APP, 'static', 'css', 'centro.css')),
]

HOOK = 'routes_centro'


def main():
    apply = len(sys.argv) > 1 and sys.argv[1] == 'apply'
    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон'}

    missing = [n for n, _ in FILES if not os.path.exists(os.path.join(SRC, n))]
    out['не_залито'] = missing
    if missing:
        out['итог'] = 'ОТКАЗ: не все файлы на месте'
        print(json.dumps(out, ensure_ascii=False))
        return

    # куда подключать роутер
    obz = os.path.join(APP, 'obzvon.py')
    main_py = os.path.join(APP, 'main.py')
    target = None
    for cand in (obz, main_py):
        if not os.path.exists(cand):
            continue
        txt = open(cand, encoding='utf-8', errors='replace').read()
        if HOOK in txt:
            target, out['уже_подключён'] = cand, True
            break
        if re.search(r'include_router\s*\(\s*(?:routes_obzvon\.)?router', txt):
            target = cand
            break
    out['точка_подключения'] = target
    if not target:
        out['итог'] = 'ОТКАЗ: не нашёл, куда подключать роутер — вставлять вслепую нельзя'
        print(json.dumps(out, ensure_ascii=False))
        return

    txt = open(target, encoding='utf-8', errors='replace').read()
    out['подключение_нужно'] = HOOK not in txt
    m = re.search(r'^(.*include_router\s*\(\s*(?:routes_obzvon\.)?router[^\n]*)$',
                  txt, re.M)
    out['якорь'] = m.group(1).strip()[:120] if m else None

    if not apply:
        out['итог'] = 'сухой прогон: ничего не менял'
        print(json.dumps(out, ensure_ascii=False))
        return

    stamp = int(time.time())
    copied = []
    for name, dst in FILES:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            shutil.copy(dst, f'{dst}.bak-{stamp}')
        shutil.copy(os.path.join(SRC, name), dst)
        copied.append(f'{name} -> {dst} ({os.path.getsize(dst)} б)')
    out['скопировано'] = copied

    if HOOK not in txt and m:
        shutil.copy(target, f'{target}.bak-{stamp}')
        line = m.group(1)
        indent = re.match(r'^(\s*)', line).group(1)
        app_var = (re.match(r'^\s*([A-Za-z_][\w.]*)\.include_router', line)
                   or re.match(r'^\s*()', line)).group(1) or 'app'
        # ПРЕФИКС берём тот же, что у боевого роутера: он монтируется как
        # include_router(routes_obzvon.router, prefix=obz), и без префикса
        # страницы centro ушли бы в корень сайта вместо /obzvon.
        pm = re.search(r'prefix\s*=\s*([A-Za-z_][\w.]*|["\'][^"\']*["\'])', line)
        prefix_expr = pm.group(1) if pm else '""'
        # у комплекта есть свой помощник include_centro(app, prefix) — он же
        # проверяет, что роуты не столкнутся со статикой и /docs
        add = (f'{line}\n'
               f'{indent}from api import routes_centro  # Центробежные 1/2\n'
               f'{indent}routes_centro.include_centro({app_var}, prefix={prefix_expr})\n')
        open(target, 'w', encoding='utf-8').write(txt.replace(line, add.rstrip('\n'), 1))
        out['роутер_подключён'] = True
        out['вставлено'] = f'routes_centro.include_centro({app_var}, prefix={prefix_expr})'
        out['бэкап_точки'] = f'{target}.bak-{stamp}'
    else:
        out['роутер_подключён'] = 'уже был'
    out['итог'] = 'файлы на месте; дальше — перезапуск службы obzvon'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
