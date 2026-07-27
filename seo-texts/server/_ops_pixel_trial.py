# -*- coding: utf-8 -*-
"""Пробный запуск сервера пикселя на 127.0.0.1:8082 + запрос к нему + остановка.

Ничего постоянного не создаёт: поднимает процесс, дёргает /o/<мусорный-токен>,
показывает ответ и гасит процесс. Нужен, чтобы убедиться, что сервис стартует
и маршрут живой, ДО создания службы.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PY = r'C:\Program Files\Python311\python.exe'
CFG = r'C:\sender\sender.yaml'
PORT = 8082


def env_with_panel():
    env = dict(os.environ)
    pep = r'C:\sender\panel.env'
    if os.path.exists(pep):
        with open(pep, encoding='utf-8-sig') as f:
            for ln in f.read().splitlines():
                ln = ln.strip()
                if ln and not ln.startswith('#') and '=' in ln:
                    k, _, v = ln.partition('=')
                    if k.strip() and v.strip():
                        env[k.strip()] = v.strip()
    return env


def main():
    out = {}
    py = PY if os.path.exists(PY) else sys.executable
    out['python'] = py
    cmd = [py, '-m', 'sender.unsub_server', '--config', CFG,
           '--host', '127.0.0.1', '--port', str(PORT)]
    out['команда'] = ' '.join(cmd)
    p = subprocess.Popen(cmd, cwd=r'C:\sender', env=env_with_panel(),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding='utf-8', errors='replace')
    time.sleep(6)
    out['процесс_жив'] = (p.poll() is None)
    if p.poll() is not None:
        so, se = p.communicate(timeout=10)
        out['stdout'] = (so or '')[-1200:]
        out['stderr'] = (se or '')[-1800:]
        out['итог'] = 'процесс упал на старте'
        print(json.dumps(out, ensure_ascii=False))
        return
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}/o/badtoken')
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            out['ответ'] = {'код': r.status, 'тип': r.headers.get('Content-Type'),
                            'байт': len(body)}
    except urllib.error.HTTPError as e:
        out['ответ'] = {'код': e.code, 'тип': e.headers.get('Content-Type'),
                        'байт': len(e.read() or b'')}
    except Exception as e:  # noqa: BLE001
        out['ответ'] = f'ошибка запроса: {str(e)[:200]}'
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:  # noqa: BLE001
            p.kill()
        out['остановлен'] = True
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
