# -*- coding: utf-8 -*-
r"""Положить БОЛЬШОЙ файл на сервер, когда дроп недоступен.

Штатный путь — дроп: файл заливается туда, сервер его скачивает через
panel_file_put {'drop': имя}. 16.08 сервер перестал ходить на дроп
(«Connection not allowed by ruleset»), а panel_file_put при этом возвращает
ok:true и прячет отказ в поле errors — я полчаса гонял старый код, считая его
новым. Отсюда два вывода, оба в этом файле: смотреть errors, а не только ok, и
уметь доставлять файл без дропа.

Как: b64 режется на куски по ~90 КБ (командная строка длиннее не выдерживает),
каждый кусок кладётся отдельным panel_file_put, затем серверный скрипт склеивает
их и сверяет sha256. Не совпало — файл не подменяется.

    python deploy_bolshoy.py <локальный файл> <путь на сервере>
"""
import base64
import hashlib
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
КУСОК = 90000


def _op(payload, timeout=600):
    p = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts',
                        json.dumps(payload, ensure_ascii=False)],
                       cwd=DIR, capture_output=True, text=True, timeout=timeout)
    i = p.stdout.find('{')
    if i < 0:
        return {'raw': p.stdout[-400:], 'err': p.stderr[-400:]}
    d = json.loads(p.stdout[i:])
    return d.get('data') or d


def доставить(локальный, назначение):
    blob = open(локальный, 'rb').read()
    sha = hashlib.sha256(blob).hexdigest()
    b64 = base64.b64encode(blob).decode()
    куски = [b64[i:i + КУСОК] for i in range(0, len(b64), КУСОК)]
    имя = os.path.basename(локальный)
    for n, k in enumerate(куски):
        r = _op({'op': 'panel_file_put', 'files': [
            {'b64': base64.b64encode(k.encode()).decode(),
             'dest': r'C:\sender\_tmp\dostavka_%s.%03d' % (имя, n)}]})
        if not r.get('ok') or r.get('errors'):
            return {'сбой_на_куске': n, 'ответ': r}
    скрипт = (
        'import base64, hashlib, json, os, shutil\n'
        'kuski = []\n'
        'for n in range(%d):\n'
        "    p = r'C:\\sender\\_tmp\\dostavka_%s.%%03d' %% n\n"
        "    kuski.append(open(p, encoding='utf-8').read())\n"
        "blob = base64.b64decode(''.join(kuski))\n"
        "sha = hashlib.sha256(blob).hexdigest()\n"
        "ok = sha == %r\n"
        "if ok:\n"
        "    open(r'%s', 'wb').write(blob)\n"
        "for n in range(%d):\n"
        "    try: os.remove(r'C:\\sender\\_tmp\\dostavka_%s.%%03d' %% n)\n"
        "    except Exception: pass\n"
        "print(json.dumps({'ok': ok, 'sha': sha[:16], 'bajt': len(blob)}, ensure_ascii=False))\n"
        % (len(куски), имя, sha, назначение.replace('\\', '\\\\'), len(куски), имя))
    r = _op({'op': 'panel_file_put', 'files': [
        {'b64': base64.b64encode(скрипт.encode('utf-8')).decode(),
         'dest': r'C:\sender\_tmp\sklejka.py'}]})
    if not r.get('ok') or r.get('errors'):
        return {'сбой_скрипта_склейки': r}
    r2 = _op({'op': 'panel_py', 'script': r'C:\sender\_tmp\sklejka.py', 'timeout': 300})
    return {'кусков': len(куски), 'sha_локальный': sha[:16], 'ответ_сервера':
            (r2.get('stdout_tail') or r2)}


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    print(json.dumps(доставить(sys.argv[1], sys.argv[2]), ensure_ascii=False)[:600])
