# -*- coding: utf-8 -*-
"""Перезапуск службы панели обзвона + проверка, что новые базы поднялись."""
import json
import subprocess
import time
import urllib.request

NSSM = 'C:\\nssm.exe'
SVC = 'obzvon'
PORT = 8012


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    raw = (r.stdout or b'') + (r.stderr or b'')
    try:
        txt = raw.decode('utf-16-le')
    except Exception:  # noqa: BLE001
        txt = raw.decode('utf-8', 'replace')
    return {'rc': r.returncode, 'out': txt.replace('\x00', '').strip()[:200]}


def get(path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}{path}', timeout=15) as r:
            body = r.read().decode('utf-8', 'replace')
            return {'код': r.status, 'байт': len(body),
                    'есть_центробежные': 'Центробежные' in body}
    except urllib.error.HTTPError as e:
        return {'код': e.code}
    except Exception as e:  # noqa: BLE001
        return {'ошибка': str(e)[:140]}


def main():
    out = {}
    out['до_рестарта'] = {'kc': get('/obzvon/kc'), 'centro1': get('/obzvon/centro1')}
    out['stop'] = sh([NSSM, 'stop', SVC])
    time.sleep(3)
    out['start'] = sh([NSSM, 'start', SVC])
    time.sleep(10)
    out['статус'] = sh([NSSM, 'status', SVC])
    # боевые базы обязаны продолжать работать — это главная проверка
    for p, label in (('/obzvon/kc', 'kc (боевая)'), ('/obzvon/meyer', 'meyer (боевая)'),
                     ('/obzvon/centro1', 'centro1'), ('/obzvon/centro2', 'centro2')):
        out[label] = get(p)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
