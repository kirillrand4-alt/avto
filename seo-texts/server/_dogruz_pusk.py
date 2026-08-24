# -*- coding: utf-8 -*-
r"""Догруз «Партии 935» полным кругом: сбор, импорт, теги, сверка."""
import json
import subprocess
import sys

p = subprocess.run([sys.executable, r'C:\sender\server\dogruz_cikl.py',
                    '--vse-pochty', '--primenit'], capture_output=True, text=True,
                   timeout=2400, cwd=r'C:\sender\server')
вывод = ((p.stdout or '') + (p.stderr or '')).strip()
try:
    o = json.loads(вывод[вывод.index('{'):])
    o.pop('пример_csv', None)
    print(json.dumps(o, ensure_ascii=False, indent=1))
except Exception:
    print(вывод[-2500:])
print(json.dumps({'rc': p.returncode}, ensure_ascii=False))
