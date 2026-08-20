# -*- coding: utf-8 -*-
r"""Ходит ли что-нибудь к провайдеру, пока стоит холд владельца.

Холд 19.08: «без использования провайдера и хмлривера пока что». XMLRiver
владелец 20.08 разрешил, провайдер — нет. HOLD-FAKTY.flag гасит fakty_cikl,
но у моста зенки есть СВОЙ путь: dorabotka() поднимает enrich_contacts с
extract_model=gpt-5.6-luna. Проверяем, был ли реальный вызов.
"""
import json
import os
import time

DIR = r'C:\sender\server'
ZENNO = r'C:\seostat\drop\zenno'
итог = {}


def хвост(п, скока=3, знаков=260):
    if not os.path.exists(п):
        return 'нет файла'
    try:
        разм = os.path.getsize(п)
        with open(п, encoding='utf-8', errors='replace') as f:
            f.seek(max(0, разм - 200000))
            стр = [s.strip() for s in f if s.strip()]
        return {'строк_в_хвосте': len(стр), 'возраст_мин': round(
            (time.time() - os.path.getmtime(п)) / 60, 1),
            'последние': [s[:знаков] for s in стр[-скока:]]}
    except Exception as e:  # noqa: BLE001
        return str(e)[:100]


итог['zenno_razbor.jsonl'] = хвост(os.path.join(DIR, 'zenno_razbor.jsonl'))
итог['dorabotka.out'] = хвост(os.path.join(ZENNO, 'dorabotka.out'), 2)

# какие extract стоят у свежих записей: 'provider' значит вызов состоялся
п = os.path.join(DIR, 'zenno_razbor.jsonl')
счёт, свежих = {}, 0
if os.path.exists(п):
    порог = time.time() - 6 * 3600
    свежий_файл = os.path.getmtime(п) >= порог
    разм = os.path.getsize(п)
    with open(п, encoding='utf-8', errors='replace') as f:
        f.seek(max(0, разм - 2000000))
        f.readline()
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            свежих += 1
            e = str(d.get('extract') or d.get('источник') or '?')[:34]
            счёт[e] = счёт.get(e, 0) + 1
    итог['файл_свежий'] = свежий_файл
итог['виды_extract_в_хвосте'] = dict(sorted(счёт.items(), key=lambda x: -x[1])[:8])
итог['записей_в_хвосте'] = свежих
итог['замок_разбора'] = (open(os.path.join(ZENNO, 'razbor.pid'),
                              encoding='utf-8').read().strip()
                         if os.path.exists(os.path.join(ZENNO, 'razbor.pid')) else 'нет')
итог['HOLD-FAKTY.flag'] = os.path.exists(os.path.join(DIR, 'HOLD-FAKTY.flag'))
print(json.dumps(итог, ensure_ascii=False, indent=1))
