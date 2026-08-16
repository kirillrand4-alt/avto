# -*- coding: utf-8 -*-
r"""Запустить УЖЕ ЛЕЖАЩИЙ на сервере скрипт с аргументами.

Отличие от run_script_on_server.py: тот заливает файл из песочницы и потому
требует, чтобы файл в песочнице был. Песочница за смену откатывалась трижды, и
каждый раз вместе с ней пропадали скрипты-обёртки — работа вставала на ровном
месте. Здесь мы ничего не заливаем: инструмент уже задеплоен, зовём его по имени.

    python na_servere.py sverka_smysla.py --zamer 400
    python na_servere.py karantin_kesha.py --stat
"""
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))


def запустить(имя, argv=(), таймаут=1500):
    путь = имя if imya_polnoe(имя) else r'C:\sender\server\%s' % имя
    payload = {'op': 'panel_py', 'script': путь, 'argv': list(argv), 'timeout': таймаут}
    p = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts',
                        json.dumps(payload, ensure_ascii=False)],
                       cwd=DIR, capture_output=True, text=True, timeout=таймаут + 300)
    i = p.stdout.find('{')
    d = json.loads(p.stdout[i:]) if i >= 0 else {'raw': p.stdout[-2000:]}
    return d.get('data') or d


def imya_polnoe(s):
    return len(s) > 2 and s[1] == ':'


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    d = запустить(sys.argv[1], sys.argv[2:])
    if d.get('stdout_tail') is not None:
        print(d['stdout_tail'])
        if d.get('stderr_tail'):
            sys.stderr.write('\n--- stderr ---\n' + d['stderr_tail'])
        return int(d.get('rc') or 0)
    print(json.dumps(d, ensure_ascii=False)[:2000])
    return 1


if __name__ == '__main__':
    sys.exit(main())
