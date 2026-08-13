# -*- coding: utf-8 -*-
"""Обогащение через БОЕВОЙ сервер задачей `enrich_contacts` — пачками, с возобновлением.

ПОЧЕМУ СЮДА, А НЕ НА VPS. Проверочный VPS перестал отвечать в 10:54 (отметка «я жив» не
обновляется, задания лежат непринятыми, «ответа нет за 850 c»). Боевой отвечает на ping.
Перезапустить VPS я не могу — доступа к машине нет, только очередь через дроп.

ЧЕМ БОЕВОЙ ЛУЧШЕ ДЛЯ ЭТОЙ ЗАДАЧИ, а не просто «запасной». `enrich_contacts` делает то,
чего мой сборщик чеко не умеет: ищет САЙТ через xmlriver (ключи лежат на сервере) и
вынимает почты С РОЛЯМИ и ФИО — закупки, директор, главный инженер. Это прямо в дыру
задачи: имён ЛПР в базе было 42 на три тысячи предприятий.

ПАЧКАМИ ПО 25, А НЕ ОДНИМ ЗАДАНИЕМ. Раннер многопоточный (RUNNER_WORKERS=8), но задание
с `companies` и без `site_crawl` уходит в ТЯЖЁЛЫЙ пул на один воркер и висит до таймаута —
это записано в его же клиенте. Поэтому шлём `site_crawl` и режем на пачки: пачка успевает
вернуться, а результат ложится на диск, а не теряется вместе с заданием.

Использование: python3 park_enrich_boevoy.py [сколько_пачек] [размер_пачки]
"""
import csv
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
CELI = os.path.join(L, 'PARK-CELI-CHECKO-2S.csv')
VYHOD = os.path.join(L, 'PARK-ENRICH-BOEVOY-2S.jsonl')
PACHEK = int(sys.argv[1]) if len(sys.argv) > 1 else 20
RAZMER = int(sys.argv[2]) if len(sys.argv) > 2 else 25


def main():
    sdelano = set()
    if os.path.exists(VYHOD):
        for l in io.open(VYHOD, encoding='utf-8'):
            try:
                sdelano.add(json.loads(l).get('inn'))
            except Exception:  # noqa: BLE001
                pass
    celi = []
    for r in csv.DictReader(io.open(CELI, encoding='utf-8-sig'), delimiter=';'):
        if r.get('inn') and r['inn'] not in sdelano:
            celi.append({'inn': r['inn'], 'name': (r.get('predpriyatie') or '').strip('"')})
    print('целей %d, уже сделано %d, пачек %d по %d'
          % (len(celi), len(sdelano), PACHEK, RAZMER), file=sys.stderr, flush=True)
    f = io.open(VYHOD, 'a', encoding='utf-8')
    sch = {'пачек': 0, 'предприятий': 0, 'с сайтом': 0, 'с почтой': 0, 'С РОЛЬЮ': 0,
           'с ФИО': 0, 'сбоев': 0}
    for n in range(PACHEK):
        kus = celi[n * RAZMER:(n + 1) * RAZMER]
        if not kus:
            break
        try:
            r = R.submit('enrich_contacts',
                         {'companies': kus, 'site_crawl': True,
                          'pace_min': 2, 'pace_max': 5}, timeout=600)
        except Exception as e:  # noqa: BLE001
            sch['сбоев'] += 1
            print('пачка %d: %s' % (n, str(e)[:90]), file=sys.stderr, flush=True)
            continue
        res = ((r or {}).get('data') or {}).get('results') or []
        if not res:
            sch['сбоев'] += 1
            print('пачка %d: пусто (%s)' % (n, str(r)[:120]), file=sys.stderr, flush=True)
            continue
        sch['пачек'] += 1
        for x in res:
            sch['предприятий'] += 1
            if x.get('site'):
                sch['с сайтом'] += 1
            em = x.get('emails') or []
            if em:
                sch['с почтой'] += 1
            if any((e.get('role') or '').strip() for e in em):
                sch['С РОЛЬЮ'] += 1
            if any((e.get('person') or '').strip() for e in em):
                sch['с ФИО'] += 1
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
        f.flush()
        print('  %s' % sch, file=sys.stderr, flush=True)
    f.close()
    print('ИТОГ: %s → %s' % (sch, VYHOD), file=sys.stderr)


main()
