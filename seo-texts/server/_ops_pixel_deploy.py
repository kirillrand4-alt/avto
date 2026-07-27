# -*- coding: utf-8 -*-
"""Поднять пиксель открытий: служба на 127.0.0.1:8082 + tracking.base_url.

Что делает:
1. Дописывает в C:\\sender\\sender.yaml ключ tracking.base_url = рабочий домен
   (сейчас пиксель строится от legal.unsub_base_url, а у того домена нет A-записи).
2. Создаёт службу SenderPixel через nssm и запускает её.

Секреты не печатает: UNSUB_SIGNING_SECRET читается из panel.env и передаётся
в службу, в вывод не попадает.

Запуск: python _ops_pixel_deploy.py [apply]
"""
import json
import os
import subprocess
import sys
import time

CFG = r'C:\sender\sender.yaml'
PANEL_ENV = r'C:\sender\panel.env'
NSSM = r'C:\nssm.exe'
PY = r'C:\Program Files\Python311\python.exe'
SVC = 'SenderPixel'
PORT = '8082'
BASE_URL = 'https://parsercompressor.online'


def patch_config(apply):
    """Добавить tracking.base_url. Разбор ПОСТРОЧНЫЙ: в секции есть комментарий,
    содержащий слово base_url, и поиск по подстроке даёт ложное срабатывание."""
    import re
    raw = open(CFG, encoding='utf-8', errors='replace').read()
    lines = raw.splitlines(keepends=True)
    res = {}

    start = None
    for i, ln in enumerate(lines):
        if re.match(r'^tracking:\s*$', ln):
            start = i
            break
    if start is None:
        res['итог'] = 'ОШИБКА: секции tracking нет'
        return res, None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and not ln[0].isspace():
            end = i
            break

    for i in range(start + 1, end):
        if re.match(r'^\s+base_url\s*:', lines[i]):     # ключ, а не комментарий
            res['итог'] = 'tracking.base_url уже задан: ' + lines[i].strip()[:80]
            return res, raw
    res['уже_настроен'] = False

    eol = '\r\n' if raw[:2000].count('\r\n') else '\n'
    new_line = f'  base_url: "{BASE_URL}"{eol}'
    lines.insert(start + 1, new_line)
    new = ''.join(lines)
    res['фрагмент'] = ''.join(lines[start:min(end + 2, len(lines))])[:300]
    if apply:
        bak = f'{CFG}.bak-{int(time.time())}'
        open(bak, 'w', encoding='utf-8', newline='').write(raw)
        open(CFG, 'w', encoding='utf-8', newline='').write(new)
        res['бэкап'] = bak
        res['записан'] = True
    return res, new


def secret_from_panel_env():
    if not os.path.exists(PANEL_ENV):
        return None
    with open(PANEL_ENV, encoding='utf-8-sig') as f:
        for ln in f.read().splitlines():
            ln = ln.strip()
            if ln.startswith('UNSUB_SIGNING_SECRET=') and '=' in ln:
                return ln.split('=', 1)[1].strip()
    return None


def make_service(apply):
    res = {}
    q = subprocess.run([NSSM, 'status', SVC], capture_output=True, text=True,
                       timeout=40)
    exists = q.returncode == 0
    res['служба_существует'] = exists
    res['статус'] = (q.stdout or q.stderr).strip()[:120]
    if not apply:
        return res
    sec = secret_from_panel_env()
    res['секрет_найден'] = bool(sec)
    if not sec:
        res['итог'] = 'ОШИБКА: UNSUB_SIGNING_SECRET не найден в panel.env'
        return res
    if not exists:
        args = f'-m sender.unsub_server --config {CFG} --host 127.0.0.1 --port {PORT}'
        for cmd in (
            [NSSM, 'install', SVC, PY, args],
            [NSSM, 'set', SVC, 'AppDirectory', r'C:\sender'],
            [NSSM, 'set', SVC, 'AppEnvironmentExtra', f'UNSUB_SIGNING_SECRET={sec}'],
            [NSSM, 'set', SVC, 'Start', 'SERVICE_AUTO_START'],
            [NSSM, 'set', SVC, 'AppStdout', r'C:\sender\_ops\pixel.log'],
            [NSSM, 'set', SVC, 'AppStderr', r'C:\sender\_ops\pixel.err.log'],
        ):
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            label = cmd[1] if cmd[1] != 'set' else f'set {cmd[3]}'
            # не печатаем значение секрета
            res.setdefault('шаги', []).append(
                {label: r.returncode})
    r = subprocess.run([NSSM, 'start', SVC], capture_output=True, text=True,
                       timeout=60)
    res['start_rc'] = r.returncode
    res['start_out'] = ((r.stdout or '') + (r.stderr or '')).strip()[:200]
    time.sleep(5)
    q2 = subprocess.run([NSSM, 'status', SVC], capture_output=True, text=True,
                        timeout=40)
    res['статус_после'] = (q2.stdout or q2.stderr).strip()[:120]
    return res


def main():
    apply = len(sys.argv) > 1 and sys.argv[1] == 'apply'
    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон'}
    out['nssm'] = os.path.exists(NSSM)
    out['python'] = os.path.exists(PY)
    cfg_res, _ = patch_config(apply)
    out['конфиг'] = cfg_res
    out['служба'] = make_service(apply)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
