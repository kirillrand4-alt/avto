# -*- coding: utf-8 -*-
"""Готов ли сервер собрать фронт: node_modules, зависимости, чужие импорты."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
WEB = r'C:\sender\sender\web'
SRC = r'C:\sender\_tmp\web-src-iz-mapy'
итог = {}
итог['node_modules'] = os.path.isdir(os.path.join(WEB, 'node_modules'))
pkg = json.loads(io.open(os.path.join(WEB, 'package.json'), encoding='utf-8').read())
зав = set(pkg.get('dependencies', {})) | set(pkg.get('devDependencies', {}))
итог['зависимости'] = sorted(зав)
итог['скрипты'] = pkg.get('scripts', {})
внешние = set()
for d, _, fs in os.walk(SRC):
    for f in fs:
        if not f.endswith(('.ts', '.tsx')):
            continue
        t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'from\s+"([^"]+)"', t):
            и = m.group(1)
            if not и.startswith('.'):
                внешние.add(и.split('/')[0] if not и.startswith('@')
                            else '/'.join(и.split('/')[:2]))
итог['импорты_в_исходниках'] = sorted(внешние)
итог['не_хватает'] = sorted(x for x in внешние if x not in зав
                            and x not in ('react', 'react-dom'))
итог['файлов_в_src_сервера'] = len(os.listdir(os.path.join(WEB, 'src')))
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
