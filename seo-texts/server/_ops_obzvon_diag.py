# -*- coding: utf-8 -*-
"""Почему не стартует служба обзвона: логи + импорт приложения напрямую."""
import json
import os
import subprocess
import sys
import traceback

APP = r'C:\seostat\app'
NSSM = 'C:\\nssm.exe'


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    raw = (r.stdout or b'') + (r.stderr or b'')
    try:
        txt = raw.decode('utf-16-le')
    except Exception:  # noqa: BLE001
        txt = raw.decode('utf-8', 'replace')
    return txt.replace('\x00', '').strip()[:300]


def main():
    out = {}
    for k in ('AppStdout', 'AppStderr', 'Application', 'AppParameters', 'AppDirectory'):
        out[k] = sh([NSSM, 'get', 'obzvon', k])

    for key in ('AppStderr', 'AppStdout'):
        p = out.get(key, '')
        if p and os.path.exists(p):
            try:
                out[f'лог_{key}'] = open(p, encoding='utf-8',
                                        errors='replace').read()[-2000:]
            except Exception as e:  # noqa: BLE001
                out[f'лог_{key}'] = str(e)[:150]

    # пробуем импортировать приложение тем же питоном, что у службы
    py = sys.executable
    code = ('import sys; sys.path.insert(0, r"%s");\n'
            'import obzvon\n'
            'print("IMPORT OK")\n') % APP
    r = subprocess.run([py, '-c', code], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=APP, timeout=120)
    out['импорт_rc'] = r.returncode
    out['импорт_stdout'] = (r.stdout or '')[-800:]
    out['импорт_stderr'] = (r.stderr or '')[-2000:]

    # что именно вставлено
    f = os.path.join(APP, 'obzvon.py')
    txt = open(f, encoding='utf-8', errors='replace').read()
    i = txt.find('routes_centro')
    out['вставка'] = txt[max(0, i - 260):i + 200] if i >= 0 else '(нет)'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
