# -*- coding: utf-8 -*-
"""Есть ли node_modules и ставим зависимости фронта."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
WEB = r'C:\sender\sender\web'
итог = {'node_modules_было': os.path.isdir(os.path.join(WEB, 'node_modules'))}
if not итог['node_modules_было']:
    p = subprocess.run(['npm.cmd', 'ci', '--no-audit', '--no-fund'], cwd=WEB,
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=1500)
    итог['ci_rc'] = p.returncode
    итог['ci_хвост'] = ((p.stdout or '') + (p.stderr or ''))[-800:]
    if p.returncode != 0:
        p2 = subprocess.run(['npm.cmd', 'install', '--no-audit', '--no-fund'],
                            cwd=WEB, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=1500)
        итог['install_rc'] = p2.returncode
        итог['install_хвост'] = ((p2.stdout or '') + (p2.stderr or ''))[-800:]
итог['node_modules_стало'] = os.path.isdir(os.path.join(WEB, 'node_modules'))
итог['есть_tsc'] = os.path.exists(os.path.join(WEB, 'node_modules', '.bin', 'tsc.cmd'))
print(json.dumps(итог, ensure_ascii=False, indent=1)[:1500])
