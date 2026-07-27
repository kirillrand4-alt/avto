# -*- coding: utf-8 -*-
"""Обогащение ядра центробежных (396 ИНН) порциями.

Зачем отдельно от launch_core_enrich.py — у того два дефекта, из-за которых
ночной прогон уже падал (см. NIGHT-RUN-STATUS.md):

1. Он шлёт ВСЕ 396 компаний одним заданием и ждёт 3000 с, тогда как сервер
   убивает задание на JOB_TIMEOUT=1800 (job_runner.py:58). Порция гарантированно
   не доживает до конца, а клиент узнаёт об этом позже сервера.
2. Он не задаёт extract_model, а дефолт для обычного списка companies —
   claude-fable-5 (enrich_contacts.py:6649). Автоподмена мёртвых моделей живёт
   ТОЛЬКО в gen_provider.resolve_model; серверный путь
   (verify_company._provider_call_stdlib) шлёт модель как есть. Поэтому модель
   задаём явно.

Резюмируемость — через тот же stream_file, что у прошлых прогонов ядра
(enrich_core2.jsonl), чтобы 245 уже готовых компаний не переобрабатывались.

Использование:
    python launch_core_chunked.py [core396.json] [batch] [workers] [bworkers] [channels] [fast]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R  # noqa: E402
from launch_sales_enrich import build_args  # noqa: E402

STREAM = 'enrich_core2.jsonl'


def load_core(path):
    """core396.json -> [{inn, name}] — без name конвейер молча пропустит компанию."""
    data = json.load(open(path, encoding='utf-8'))
    out, seen = [], set()
    for c in data:
        inn = str(c.get('inn') or '').strip()
        name = (c.get('name') or '').strip()
        if not inn or not name or inn in seen:
            continue
        seen.add(inn)
        out.append({'inn': inn, 'name': name,
                    'ogrn': c.get('ogrn') or '', 'site': c.get('site') or ''})
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'core396.json'
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    bworkers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    channels = int(sys.argv[5]) if len(sys.argv) > 5 else 6
    fast = (sys.argv[6].lower() in ('1', 'fast', 'true')) if len(sys.argv) > 6 else True

    comps = load_core(path)
    print(f'ядро центробежных: {len(comps)} компаний с ИНН+названием', flush=True)

    chunks = [comps[i:i + batch] for i in range(0, len(comps), batch)]
    for rnd, chunk in enumerate(chunks, 1):
        args = build_args(chunk, workers, bworkers, channels, fast=fast)
        args['stream_file'] = STREAM          # резюм поверх прошлых прогонов ядра
        args['source'] = 'centrifugal-core'
        print(f'\n=== порция {rnd}/{len(chunks)}: {len(chunk)} компаний, '
              f'профиль={"быстрый" if fast else "полный"} ===', flush=True)
        t0 = time.time()
        out = R.submit('enrich_contacts', args, wait=True, poll=20, timeout=1750)
        took = time.time() - t0
        if not isinstance(out, dict) or not out.get('ok'):
            print(f'порция {rnd} НЕ ок за {took:.0f}с: '
                  f'{json.dumps(out, ensure_ascii=False)[:400]}', flush=True)
            continue                           # resume подберёт на следующем проходе
        data = out.get('data') or {}
        got = data.get('results') or []
        print(f'порция {rnd}: вернулось {len(got) if isinstance(got, list) else 0} '
              f'за {took:.0f}с', flush=True)


if __name__ == '__main__':
    main()
