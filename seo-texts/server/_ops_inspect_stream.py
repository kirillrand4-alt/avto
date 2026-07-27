# -*- coding: utf-8 -*-
"""Разбор потока обогащения (ТОЛЬКО отчёт): что конвейер реально вернул по компаниям.

Нужен, чтобы понять узкое место по времени и дошёл ли вызов провайдера.
Запуск: python _ops_inspect_stream.py <stream.jsonl> [сколько_последних]
"""
import json
import os
import sys

SRV = r'C:\sender\server'


def main():
    fn = sys.argv[1] if len(sys.argv) > 1 else 'enrich_sales.jsonl'
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    p = fn if os.path.isabs(fn) else os.path.join(SRV, fn)
    if not os.path.exists(p):
        print(json.dumps({'error': f'нет файла {p}'}, ensure_ascii=False))
        return

    recs = []
    for ln in open(p, encoding='utf-8', errors='replace'):
        try:
            recs.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue

    out = {'файл': p, 'записей': len(recs)}
    agg = {'с_email': 0, 'с_ролями_от_провайдера': 0, 'regex': 0,
           'regex_provider_fail': 0, 'сайт_не_найден': 0, 'блок_сайта': 0}
    t_sum = {}
    rows = []
    for r in recs[-last:]:
        tm = r.get('timings') or {}
        for k, v in tm.items():
            try:
                t_sum[k] = round(t_sum.get(k, 0) + float(v), 1)
            except Exception:  # noqa: BLE001
                pass
        rows.append({
            'инн': r.get('inn'),
            'имя': (r.get('name') or '')[:38],
            'сайт': r.get('site') or '',
            'сайт_откуда': r.get('site_source') or '',
            'email': len(r.get('emails') or []),
            'извлечение': r.get('extract') or '',
            'owner_match': r.get('owner_match'),
            'конкурент': r.get('is_compressor_maker'),
            'телефонов': len(r.get('phones') or []),
            'закупки': len(r.get('zakupki') or []) if isinstance(r.get('zakupki'), list) else r.get('zakupki'),
            'hh': r.get('hh') if not isinstance(r.get('hh'), dict) else 'есть',
            'опо': (r.get('opo') or {}).get('opo') if isinstance(r.get('opo'), dict) else None,
            'тайминги': {k: round(float(v), 1) for k, v in tm.items() if v},
            'ошибка': (r.get('error') or r.get('method') or '')[:60],
        })

    for r in recs:
        if r.get('emails'):
            agg['с_email'] += 1
        e = r.get('extract') or ''
        if e == 'provider':
            agg['с_ролями_от_провайдера'] += 1
        elif e == 'regex':
            agg['regex'] += 1
        elif e == 'regex-provider-fail':
            agg['regex_provider_fail'] += 1
        if not r.get('site'):
            agg['сайт_не_найден'] += 1
        if str(r.get('method') or '').startswith('site-block'):
            agg['блок_сайта'] += 1

    out['итого'] = agg
    out['сумма_таймингов_по_последним'] = t_sum
    out['последние'] = rows
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
