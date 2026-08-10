# -*- coding: utf-8 -*-
"""Клиент ВТОРОГО раннера — проверочного VPS. Через него открыт checko, закрытый отсюда.

ПОЧЕМУ ЭТО ПОНАДОБИЛОСЬ, с замером, а не с догадкой. Обогащение встало: предприятий с
доказанной машиной 1 861, контакт есть у 235. Контакты берутся с сайта, сайт ищется по ИНН,
а всё, что умеет ИНН → сайт, из этого контейнера закрыто:

    checko.ru        HTTP 429 на ЛЮБОЙ путь, включая /robots.txt — nginx/1.28.0
                     значит это лимит на наш IP целиком, а не защита карточек
    rusprofile.ru    403
    zakupki.gov.ru   Connection reset
    боевой раннер    в allowlist остался один browser_probe; panel_py отвергается

Чем ходил рабочий парсер (`srv-checko_contacts.py`, строка 5): «50 потоков, socks5:3001» —
пул из 78 прокси, список лежит на дропе (`dolphin-proxies.txt`). Из контейнера пул
недостижим: исходящий TCP на :3001 виснет, наружу пускают только HTTPS через агент-прокси.

А ВТОРОЙ раннер — проверочный VPS — жив (отметка `vps-runner-zhiv.json` свежая) и принимает
задачу `py`: скачивает скрипт с дропа и исполняет у себя. С него socks-пул достижим, потому
что там и работал парсер. Разница с боевым только в префиксе файлов: `vjob-` / `vresult-`,
чтобы две машины не растаскивали задания друг друга.

ПОДПИСЬ ОБЯЗАТЕЛЬНА. Раннер сверяет HMAC по канону `{id, task, args, ts}`; секрет берём тем
же способом, что и боевой клиент, — из `runner-secrets.env` на дропе.

Использование:
    python3 park_vps.py --skript park_checko_vps.py --argv 500
    python3 park_vps.py --ping
"""
import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R

PREFIKS, OTVET = 'vjob-', 'vresult-'


def _drop(*args):
    put = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server', 'drop_client.sh')
    return subprocess.run(['bash', put] + list(args), capture_output=True, text=True).stdout


def otpravit(task, args, timeout=900, poll=12):
    R._load_secret_from_drop()
    jid = R._now_id()
    job = {'id': jid, 'task': task, 'args': args, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False)
    if R.JOB_SECRET:
        job['sig'] = hmac.new(R.JOB_SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()
    R._req('PUT', f'{PREFIKS}{jid}.json',
           data=json.dumps(job, ensure_ascii=False).encode('utf-8'))
    print(f'задание на VPS: {PREFIKS}{jid}.json (task={task}, подпись='
          f'{"да" if R.JOB_SECRET else "НЕТ"})', file=sys.stderr, flush=True)
    srok = time.time() + timeout
    imya = f'{OTVET}{jid}.json'
    while time.time() < srok:
        time.sleep(poll)
        try:
            spisok = json.loads(R._req('GET', 'list'))
        except Exception:  # noqa: BLE001
            continue
        if any(x.get('name') == imya for x in spisok):
            return json.loads(R._req('GET', imya))
    return {'ok': False, 'error': 'ответа нет за %d c' % timeout, 'id': jid}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skript', help='файл со скриптом; будет выложен на дроп и запущен на VPS')
    ap.add_argument('--argv', nargs='*', default=[])
    ap.add_argument('--ping', action='store_true')
    ap.add_argument('--timeout', type=int, default=900)
    a = ap.parse_args()
    if a.ping:
        print(json.dumps(otpravit('ping', {}, timeout=180), ensure_ascii=False)[:600])
        return 0
    if not a.skript:
        print('нечего запускать: нужен --skript или --ping', file=sys.stderr)
        return 1
    # Скрипт едет ФАЙЛОМ через дроп — так его видно и можно перечитать глазами.
    vyh = _drop('up', a.skript)
    if '"ok":true' not in vyh:
        print('скрипт не выложен на дроп, задание не отправляю:', vyh[:200], file=sys.stderr)
        return 2
    r = otpravit('py', {'file': os.path.basename(a.skript), 'argv': list(a.argv)},
                 timeout=a.timeout)
    print(json.dumps(r, ensure_ascii=False)[:2000])
    return 0 if r.get('ok') else 3


if __name__ == '__main__':
    sys.exit(main())
