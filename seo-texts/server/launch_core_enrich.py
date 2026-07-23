# -*- coding: utf-8 -*-
"""Запуск полного обогащения 396 центробежных (ядро) — все источники, resume, write_db.
Читает список компаний из core396.json (inn/name/sector/revenue), сабмитит одним
enrich_contacts-заданием раннеру. Резюмируемо (пропускает готовые ИНН из enrich_core.jsonl).

Использование:
    python launch_core_enrich.py <core396.json> [workers] [browser_workers] [channels]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'core396.json'
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    bworkers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    channels = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    companies = json.load(open(path, encoding='utf-8'))
    # нормализация: enrich_one ждёт inn/name/site(опц)
    comps = []
    for c in companies:
        comps.append({'inn': str(c.get('inn') or '').strip(),
                      'name': c.get('name') or '',
                      'ogrn': c.get('ogrn') or '',
                      'site': c.get('site') or ''})
    comps = [c for c in comps if c['inn']]
    args = {
        'companies': comps,
        'workers': workers, 'browser_workers': bworkers, 'channels': channels,
        'pace_min': 2, 'pace_max': 5,
        'zakupki_check': True, 'smtp_check': True, 'opo_check': True,
        'no_vk_lookup': True,   # VK идёт через ОДИН закреплённый профиль -> при 80 воркерах
                                # сериализуется/виснет; для массы выключаем (справочник покрывает).
        'write_db': True, 'resume': True,
        'stream_file': 'enrich_core2.jsonl', 'source': 'centrifugal-core',
    }
    print(f'submitting {len(comps)} companies, workers={workers} bworkers={bworkers} channels={channels}')
    out = R.submit('enrich_contacts', args, wait=True, poll=20, timeout=int(sys.argv[5]) if len(sys.argv) > 5 else 3000)
    print(json.dumps(out, ensure_ascii=False)[:2000] if isinstance(out, (dict, list)) else str(out)[:2000])

if __name__ == '__main__':
    main()
