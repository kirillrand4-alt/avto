# -*- coding: utf-8 -*-
"""Запустить локальный python-скрипт НА СЕРВЕРЕ владельца.

Зачем отдельный файл: раннер умеет только задачи из своего allowlist, а разовые
разборы удобнее писать обычным скриптом. Здесь скрипт заливается инлайном (b64)
в C:\\sender\\_tmp\\ через op `panel_file_put` и запускается через op `panel_py`
питоном панели с её окружением (PROVIDER_API_KEY, XMLRIVER_*, DROP_*).

Живёт в репозитории, а не в песочнице: за смену его трижды теряло рестартом
контейнера, и каждый раз приходилось писать заново.

ВАЖНО про длительные прогоны: раннер режет ЛЮБОЕ задание по RUNNER_JOB_TIMEOUT
(30 минут). Долгую работу запускать не через этот путь, а отдельным процессом
(subprocess.Popen с DETACHED_PROCESS) — такой переживает и таймаут, и рестарт
песочницы.

Использование:
    python run_script_on_server.py <файл.py> [timeout_sec]
"""
import base64
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    tmo = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    dest = r'C:\sender\_tmp\%s' % os.path.basename(src)
    blob = open(src, 'rb').read()

    def run(payload):
        p = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts',
                            json.dumps(payload, ensure_ascii=False)],
                           cwd=DIR, capture_output=True, text=True, timeout=tmo + 300)
        i = p.stdout.find('{')
        return json.loads(p.stdout[i:]) if i >= 0 else {'raw': p.stdout[-2000:],
                                                        'err': p.stderr[-800:]}

    r1 = run({'op': 'panel_file_put',
              'files': [{'b64': base64.b64encode(blob).decode(), 'dest': dest}]})
    if not (r1.get('data') or {}).get('ok'):
        print(json.dumps(r1, ensure_ascii=False, indent=1))
        return 1
    r2 = run({'op': 'panel_py', 'script': dest, 'timeout': tmo})
    d = r2.get('data') or r2
    if d.get('stdout_tail') is not None:
        print(d['stdout_tail'])
        if d.get('stderr_tail'):
            sys.stderr.write('\n--- stderr ---\n' + d['stderr_tail'])
        if d.get('rc'):
            sys.stderr.write('\nrc=%s\n' % d['rc'])
            return int(d['rc'])
    else:
        print(json.dumps(r2, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
