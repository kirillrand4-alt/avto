# -*- coding: utf-8 -*-
"""Дать службе SenderPixel полное окружение из panel.env и перезапустить.

Причина: Config.load валидирует ВСЕ ящики и требует каждый BOX*_PASSWORD, хотя
серверу пикселя ящики не нужны. Проще отдать то же окружение, что у панели, чем
менять валидацию конфига на боевой системе.

Значения переменных не печатаются — только имена.
"""
import json
import os
import subprocess
import time

NSSM = 'C:\\nssm.exe'
SVC = 'SenderPixel'
PANEL_ENV = 'C:\\sender\\panel.env'


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    raw = (r.stdout or b'') + (r.stderr or b'')
    try:
        txt = raw.decode('utf-16-le')
    except Exception:  # noqa: BLE001
        txt = raw.decode('utf-8', 'replace')
    return {'rc': r.returncode, 'out': txt.replace('\x00', '').strip()[:200]}


def main():
    out = {}
    pairs = []
    with open(PANEL_ENV, encoding='utf-8-sig') as f:
        for ln in f.read().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith('#') and '=' in ln:
                k, _, v = ln.partition('=')
                k, v = k.strip(), v.strip()
                if k and v:
                    pairs.append(f'{k}={v}')
    out['переменных_передано'] = len(pairs)
    out['имена'] = sorted(p.split('=', 1)[0] for p in pairs)

    sh([NSSM, 'stop', SVC])
    time.sleep(2)
    out['set_env'] = sh([NSSM, 'set', SVC, 'AppEnvironmentExtra'] + pairs)
    out['start'] = sh([NSSM, 'start', SVC])
    time.sleep(6)
    out['статус'] = sh([NSSM, 'status', SVC])

    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:8082/o/probe', timeout=10) as x:
            out['бэкенд'] = {'код': x.status, 'тип': x.headers.get('Content-Type'),
                             'байт': len(x.read())}
    except Exception as e:  # noqa: BLE001
        out['бэкенд'] = str(e)[:200]
        p = 'C:\\sender\\_ops\\pixel.err.log'
        if os.path.exists(p):
            out['лог_хвост'] = open(p, encoding='utf-8', errors='replace').read()[-800:]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
