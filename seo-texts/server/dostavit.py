# -*- coding: utf-8 -*-
r"""Положить локальный файл НА СЕРВЕР по произвольному пути.

Тот же путь, что у run_script_on_server (op `panel_file_put`), но без запуска:
нужен, когда файл — это код панели, а не разовый разбор. Живёт в репозитории
по той же причине, что и раннер: откат песочницы стирал его уже трижды, и
каждый раз деплой приходилось изобретать заново.

    python dostavit.py <локальный файл> <путь на сервере> [ещё пара...]

Проверяем не «команда прошла», а совпадение sha256 с тем, что легло на диск.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
ПОРЦИЯ = 700 * 1024


def _op(payload, tmo=900):
    p = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts',
                        json.dumps(payload, ensure_ascii=False)],
                       cwd=DIR, capture_output=True, text=True, timeout=tmo)
    i = p.stdout.find('{')
    return (json.loads(p.stdout[i:]) if i >= 0
            else {'raw': p.stdout[-1500:], 'err': p.stderr[-600:]})


def положить(локальный, удалённый):
    данные = open(локальный, 'rb').read()
    свой = hashlib.sha256(данные).hexdigest()[:16]
    if len(данные) > ПОРЦИЯ:
        return {'файл': локальный, 'ОШИБКА': 'больше %d байт — нужен кусочный '
                'деплой' % ПОРЦИЯ}
    r = _op({'op': 'panel_file_put',
             'files': [{'b64': base64.b64encode(данные).decode(),
                        'dest': удалённый}]})
    ок = (r.get('data') or {}).get('ok')
    # сверка: читаем то, что легло, и считаем sha на сервере
    проверка = _op({'op': 'panel_py_inline', 'code': ''} if False else {
        'op': 'panel_file_get', 'path': удалённый}) if ок else {}
    чужой = ''
    тело = (проверка.get('data') or {}).get('b64')
    if тело:
        чужой = hashlib.sha256(base64.b64decode(тело)).hexdigest()[:16]
    return {'файл': os.path.basename(локальный), 'куда': удалённый,
            'байт': len(данные), 'положено': bool(ок),
            'sha_локальный': свой, 'sha_на_сервере': чужой or '(не сверил)',
            'СОВПАЛО': (чужой == свой) if чужой else None}


def main():
    пары = sys.argv[1:]
    if len(пары) < 2 or len(пары) % 2:
        print(__doc__)
        return 2
    итог = [положить(пары[i], пары[i + 1]) for i in range(0, len(пары), 2)]
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0 if all(x.get('положено') for x in итог) else 1


if __name__ == '__main__':
    sys.exit(main())
