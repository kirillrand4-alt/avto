# -*- coding: utf-8 -*-
"""Запуск штатного обогащения базы продажников (555 ИНН) конвейером enrich_contacts.

Пара к launch_core_enrich.py, но источник — sales_base.json (словарь лист -> записи
{inn, name, emails[], phones[]}). Гоняем ПОРЦИЯМИ: JOB_TIMEOUT раннера 1800 с, поэтому
батч берём с запасом и полагаемся на resume (пропуск готовых ИНН из stream_file).

Использование:
    python launch_sales_enrich.py <sales_base.json> [batch] [workers] [bworkers] [channels]

Дельфин: профиль 829115401 (VK, закреплён по IP) исключён из пула явно — владелец
просил его не трогать.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R  # noqa: E402

INN_RE = re.compile(r'^(\d{10}|\d{12})$')
VK_PINNED = '829115401'
STREAM = 'enrich_sales.jsonl'

# 20 профилей владельца минус VK-закреплённый (см. dolphin_proxy_check)
DOLPHIN_POOL = [
    '829115394', '829115383', '829115375', '829115353', '829115344',
    '829115332', '829115325', '829115313', '829115296',
]


def load_companies(path):
    """sales_base.json -> [{inn, name}] без дублей, только с названием."""
    d = json.load(open(path, encoding='utf-8'))
    rows = []
    if isinstance(d, dict):
        for sheet, items in d.items():
            for it in (items or []):
                if isinstance(it, dict):
                    rows.append((sheet, it))
    else:
        rows = [('(список)', x) for x in d if isinstance(x, dict)]

    out, seen = [], set()
    for sheet, r in rows:
        inn = str(r.get('inn') or '').strip()
        if not INN_RE.match(inn) or inn in seen:
            continue
        name = (r.get('name') or '').strip()
        if not name:
            continue          # без name конвейер молча пропустит компанию
        seen.add(inn)
        out.append({'inn': inn, 'name': name, 'site': '', 'ogrn': ''})
    return out


def build_args(comps, workers, bworkers, channels):
    return {
        'companies': comps,
        'workers': workers, 'browser_workers': bworkers, 'channels': channels,
        'pace_min': 2, 'pace_max': 5,
        'fetch_timeout': 25,          # мёртвые сайты не держат воркер
        'zakupki_check': True,        # контакт закупщика из ЕИС внутри конвейера
        'hh_check': True,             # компрессорные вакансии = сигнал «оборудование есть»
        'opo_check': True,
        'smtp_check': True,
        'no_vk_lookup': True,         # VK — один закреплённый профиль, на массе сериализуется
        'extract_model': 'claude-haiku-4-5',   # массовый вал: 9x дешевле fable
        'dolphin_profiles': DOLPHIN_POOL,
        'write_db': True, 'resume': True,
        'stream_file': STREAM, 'source': 'sales-base',
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'sales_base.json'
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    bworkers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    channels = int(sys.argv[5]) if len(sys.argv) > 5 else 6

    # cap в конвейере действует только для mass_base/news_enrich — обычный список
    # companies он игнорирует, поэтому режем порции ЗДЕСЬ.
    only = sys.argv[6] if len(sys.argv) > 6 else ''
    comps = load_companies(path)
    if only:
        keep = {i.strip() for i in only.split(',') if i.strip()}
        comps = [c for c in comps if c['inn'] in keep] if keep else comps
    print(f'база продажников: {len(comps)} компаний с ИНН+названием')

    done_total = 0
    chunks = [comps[i:i + batch] for i in range(0, len(comps), batch)]
    for rnd, chunk in enumerate(chunks, 1):
        args = build_args(chunk, workers, bworkers, channels)
        print(f'\n=== порция {rnd}/{len(chunks)}: {len(chunk)} компаний, '
              f'workers={workers} bworkers={bworkers} ===', flush=True)
        t0 = time.time()
        out = R.submit('enrich_contacts', args, wait=True, poll=20, timeout=1750)
        took = time.time() - t0
        if not isinstance(out, dict) or not out.get('ok'):
            print(f'порция {rnd} НЕ ок за {took:.0f}с: '
                  f'{json.dumps(out, ensure_ascii=False)[:600]}', flush=True)
            continue          # resume подберёт её на следующем проходе
        data = out.get('data') or {}
        got = data.get('results') or data.get('companies') or []
        n = len(got) if isinstance(got, list) else 0
        done_total += n
        print(f'порция {rnd}: вернулось {n} за {took:.0f}с '
              f'(накопительно {done_total})', flush=True)
        for k in ('cost', 'stats', 'summary'):
            if data.get(k):
                print(f'   {k}:', json.dumps(data[k], ensure_ascii=False)[:400],
                      flush=True)


if __name__ == '__main__':
    main()
