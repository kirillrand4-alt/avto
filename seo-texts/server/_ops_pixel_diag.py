# -*- coding: utf-8 -*-
"""Диагностика службы SenderPixel: статус, параметры, логи."""
import json
import os
import subprocess

NSSM = 'C:\\nssm.exe'
SVC = 'SenderPixel'


def sh(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        raw = (r.stdout or b'') + (r.stderr or b'')
        # nssm печатает UTF-16LE
        try:
            txt = raw.decode('utf-16-le').strip()
        except Exception:  # noqa: BLE001
            txt = raw.decode('utf-8', 'replace').strip()
        return {'rc': r.returncode, 'out': txt.replace('\x00', '')[:400]}
    except Exception as e:  # noqa: BLE001
        return {'error': str(e)[:200]}


def main():
    out = {}
    out['статус'] = sh([NSSM, 'status', SVC])
    for k in ('Application', 'AppParameters', 'AppDirectory'):
        out[k] = sh([NSSM, 'get', SVC, k])
    for f in ('C:\\sender\\_ops\\pixel.err.log', 'C:\\sender\\_ops\\pixel.log'):
        if os.path.exists(f):
            try:
                out[f] = open(f, encoding='utf-8', errors='replace').read()[-1500:]
            except Exception as e:  # noqa: BLE001
                out[f] = str(e)[:150]
        else:
            out[f] = '(нет файла)'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
