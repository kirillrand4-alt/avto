# -*- coding: utf-8 -*-
"""ЭТАП 2 конвейера отзывов — разбор провайдером. Запускается В ПЕСОЧНИЦЕ, не
на сервере.

Почему здесь, а не в серверном скрипте: с сервера провайдерский шлюз
недоступен — прогон 30.07 дал 9 TimeoutError из 9 вызовов, тогда как из
песочницы тот же вызов отвечает за 5-8 секунд. Ключ PROVIDER_API_KEY есть в
обоих местах, дело не в нём. Разрезать конвейер дешевле, чем чинить сеть
сервера, и раннер (общий на пять агентов) при этом не занят.

Вход:  reviews_raw.jsonl с дропа (пишет `_ops_reviews_harvest.py --stage ocr`).
Выход: reviews_parsed.json на дроп (читает `--stage persist`).

    python reviews_parse_local.py [--limit N] [--workers 6]
"""
import json
import os
import subprocess
import sys
import threading
import time

СЕРВЕР = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, СЕРВЕР)

import _ops_reviews_harvest as H  # noqa: E402

РАБ = os.environ.get('REVIEWS_WORKDIR') or '/tmp/reviews_work'
КЛИЕНТ = os.path.join(СЕРВЕР, 'drop_client.sh')


def дроп(*args):
    return subprocess.run(['bash', КЛИЕНТ] + list(args), capture_output=True,
                          text=True, timeout=300)


def main():
    аргв = sys.argv[1:]
    лимит, воркеров = 0, 6
    for i, a in enumerate(аргв):
        if a == '--limit' and i + 1 < len(аргв):
            лимит = int(аргв[i + 1])
        if a == '--workers' and i + 1 < len(аргв):
            воркеров = int(аргв[i + 1])
    os.makedirs(РАБ, exist_ok=True)
    сырьё = os.path.join(РАБ, 'reviews_raw.jsonl')
    разбор = os.path.join(РАБ, 'reviews_parsed.json')
    дроп('down', 'reviews_raw.jsonl', сырьё)

    строки = []
    for s in open(сырьё, encoding='utf-8'):
        s = s.strip()
        if not s:
            continue
        try:
            строки.append(json.loads(s))
        except Exception:  # noqa: BLE001
            pass
    # один и тот же кусок мог приехать дважды (перезапуск этапа ocr) — схлопываем
    видел, куски = set(), []
    for з in строки:
        k = (з.get('url'), (з.get('текст') or '')[:200])
        if k in видел:
            continue
        видел.add(k)
        куски.append(з)
    if лимит:
        куски = куски[:лимит]
    print(f'кусков: {len(куски)} (из {len(строки)} строк сырья)', flush=True)

    итог, лок, счёт = [], threading.Lock(), {'ok': 0, 'пусто': 0, 'ошибка': 0}

    def работа(з):
        try:
            люди = H.провайдер(з.get('текст') or '')
        except Exception:  # noqa: BLE001
            with лок:
                счёт['ошибка'] += 1
            return
        with лок:
            if люди:
                счёт['ok'] += 1
            else:
                счёт['пусто'] += 1
            for эл in люди:
                if not isinstance(эл, dict):
                    continue
                эл['_url'] = з.get('url')
                эл['_вид'] = з.get('вид')
                эл['_сайт'] = з.get('сайт')
                итог.append(эл)

    потоки = []
    for з in куски:
        while len([p for p in потоки if p.is_alive()]) >= воркеров:
            time.sleep(0.2)
        p = threading.Thread(target=работа, args=(з,), daemon=True)
        p.start()
        потоки.append(p)
    for p in потоки:
        p.join(timeout=200)

    with open(разбор, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    print('разобрано людей:', len(итог), счёт, flush=True)
    r = дроп('up', разбор)
    print('на дроп:', (r.stdout or r.stderr)[:200], flush=True)
    for э in итог[:8]:
        print('  ', json.dumps(э, ensure_ascii=False)[:220], flush=True)


if __name__ == '__main__':
    main()
