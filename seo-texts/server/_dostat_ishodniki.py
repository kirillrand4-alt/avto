# -*- coding: utf-8 -*-
r"""Достать НАСТОЯЩИЕ исходники фронта из sourcemap действующей сборки.

Исходники на сервере от 22.07, а в панели работает сборка от 11.08 — три недели
правок (включая крестик в ленте) живут только в бандле. Собирать из устаревших
исходников нельзя: это откат. Но vite кладёт рядом .js.map, а в нём поле
sourcesContent — полные тексты исходных .tsx. Их и достаём.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
DIST = r'C:\sender\web\dist'
КУДА = r'C:\sender\_tmp\web-src-iz-mapy'
html = io.open(os.path.join(DIST, 'index.html'), encoding='utf-8',
               errors='replace').read()
m = re.search(r'assets/(index-[\w-]+\.js)', html)
итог = {'index.html_ссылается_на': m.group(1) if m else 'не найдено'}
if not m:
    print(json.dumps(итог, ensure_ascii=False))
    raise SystemExit(1)
карта = os.path.join(DIST, 'assets', m.group(1) + '.map')
итог['карта_есть'] = os.path.exists(карта)
if os.path.exists(карта):
    d = json.loads(io.open(карта, encoding='utf-8', errors='replace').read())
    исходники = d.get('sources') or []
    тексты = d.get('sourcesContent') or []
    итог['файлов_в_карте'] = len(исходники)
    наши = [(s, t) for s, t in zip(исходники, тексты)
            if s and t and '/src/' in s.replace('\\', '/')
            and 'node_modules' not in s]
    итог['наших_файлов'] = len(наши)
    os.makedirs(КУДА, exist_ok=True)
    записано = []
    for s, t in наши:
        отн = s.replace('\\', '/').split('/src/', 1)[-1]
        путь = os.path.join(КУДА, отн.replace('/', os.sep))
        os.makedirs(os.path.dirname(путь), exist_ok=True)
        io.open(путь, 'w', encoding='utf-8').write(t)
        записано.append(отн)
    итог['куда'] = КУДА
    итог['записано'] = sorted(записано)
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
