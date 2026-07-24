# -*- coding: utf-8 -*-
"""ТОП-1000 базы по выручке — полное обогащение батчами (владелец 2026-07-23).
Батчи по N с resume на общий stream_file: рестарт раннера не создаёт петлю (урок
ночного прогона: один гигантский job при падении раннера переисполнялся целиком).

    python launch_top1000.py <top1000.json> [batch=250] [workers=30]
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R


def main():
    path = sys.argv[1]
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    comps = json.load(open(path, encoding='utf-8'))
    clean = []
    for c in comps:
        site = (c.get('site') or '').split('|')[0].strip()   # «a | b» -> первый
        clean.append({'inn': str(c.get('inn') or '').strip(), 'name': c.get('name') or '',
                      'city': c.get('city') or '', 'region': c.get('region') or '',
                      'phones': c.get('phones') or [], 'site': site})
    clean = [c for c in clean if c['inn'] and c['name']]
    jobs = []
    for i in range(0, len(clean), batch):
        chunk = clean[i:i + batch]
        args = {
            'companies': chunk,
            'workers': workers, 'browser_workers': 4, 'channels': 8,
            'pace_min': 2, 'pace_max': 5,
            'zakupki_check': True, 'smtp_check': True, 'opo_check': True,
            'no_vk_lookup': True,   # VK через один закреплённый профиль — сериализуется на массе
            'write_db': True, 'resume': True,
            'stream_file': 'enrich_top1000.jsonl', 'source': 'top1000',
        }
        out = R.submit('enrich_contacts', args, wait=False)
        jobs.append(out if isinstance(out, str) else str(out))
        print(f'batch {i // batch + 1}: {len(chunk)} компаний -> {out}')
        time.sleep(1.5)   # _now_id = секунда+pid: без паузы id батчей совпадут (перезатрут job)
    print('всего батчей:', len(jobs))


if __name__ == '__main__':
    main()
