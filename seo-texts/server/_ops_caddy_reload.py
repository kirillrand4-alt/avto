# -*- coding: utf-8 -*-
"""Graceful reload конфига Caddy (без рестарта службы) + проверка маршрута."""
import json
import subprocess
import urllib.request

CADDY = 'C:\\caddy.exe'
CFG = 'C:\\Caddyfile'


def main():
    out = {}
    r = subprocess.run([CADDY, 'reload', '--config', CFG, '--adapter', 'caddyfile'],
                       capture_output=True, text=True, timeout=120, cwd='C:\\')
    out['reload_rc'] = r.returncode
    out['reload'] = ((r.stdout or '') + (r.stderr or ''))[-800:]

    # локальная проверка бэкенда пикселя
    try:
        with urllib.request.urlopen('http://127.0.0.1:8082/o/probe', timeout=10) as x:
            out['бэкенд_8082'] = {'код': x.status, 'тип': x.headers.get('Content-Type'),
                                  'байт': len(x.read())}
    except Exception as e:  # noqa: BLE001
        out['бэкенд_8082'] = str(e)[:200]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
