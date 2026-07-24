# -*- coding: utf-8 -*-
"""Перепрогонка компаний, у которых extract=regex-provider-fail (провайдер падал
из-за сломанного транспорта до фикса 2026-07-24). Сайт у всех уже известен из
предыдущего краула — discovery (xmlriver) не тратим, только повторный краул +
провайдер (теперь работающий) для извлечения ролей/ЛПР/activity.

Компании из refail_companies.json. Пишем в enrich_recheck.jsonl — новые
provider-строки перекрывают старые fail (последний исход по ИНН выигрывает в
агрегатах и export_core). Шлём ЧАНКАМИ отдельными job'ами (предсказуемо по
таймауту раннера, без resume-капа, который пропускал бы fail с ≥3 попытками).

Использование:
    python launch_refail.py <refail_companies.json> [chunk] [workers] [bworkers]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'refail_companies.json'
    chunk = int(sys.argv[2]) if len(sys.argv) > 2 else 105
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    bworkers = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    companies = json.load(open(path, encoding='utf-8'))
    comps = [{'inn': str(c.get('inn') or '').strip(), 'name': c.get('name') or '',
              'site': c.get('site') or '', 'city': c.get('city') or ''}
             for c in companies if str(c.get('inn') or '').strip() and c.get('site')]
    n = len(comps)
    print(f'refail: {n} компаний, чанк={chunk}, workers={workers} bworkers={bworkers}')
    for i in range(0, n, chunk):
        batch = comps[i:i + chunk]
        args = {
            'companies': batch,
            'workers': workers, 'browser_workers': bworkers, 'channels': 6,
            'pace_min': 1.5, 'pace_max': 3.5,
            'zakupki_check': True, 'smtp_check': True, 'opo_check': True,
            'no_vk_lookup': True,       # массовая волна — VK через один профиль виснет
            'no_dir_lookup': False,     # справочники оставляем (добор телефонов/email)
            'no_site_cache': True,      # ОБЯЗАТЕЛЬНО: кеш обошёл бы новый краул с фиксом
            'write_db': True,
            'stream_file': 'enrich_recheck.jsonl', 'source': 'refail',
        }
        tag = f'{i // chunk + 1}/{(n + chunk - 1) // chunk}'
        print(f'  чанк {tag}: {len(batch)} компаний, submit...')
        out = R.submit('enrich_contacts', args, wait=True, poll=20, timeout=2000)
        if isinstance(out, dict):
            dd = out.get('data') or {}
            print(f'  чанк {tag} готов: took={out.get("took_sec")} '
                  f'count={dd.get("count")} summary={json.dumps(dd.get("summary") or {}, ensure_ascii=False)[:150]}')
        else:
            print(f'  чанк {tag}: {str(out)[:200]}')


if __name__ == '__main__':
    main()
