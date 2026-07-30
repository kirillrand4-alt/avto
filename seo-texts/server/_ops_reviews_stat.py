# -*- coding: utf-8 -*-
"""Замер источника «отзывы поставщиков» ПО БАЗЕ, а не по счётчикам прогона.

Счётчик прогона врёт в обе стороны: он не видит дублей, схлопнутых на UPSERT,
и не знает, что часть записей уже была. Поэтому цифры для отчёта берём из
enrich.db, а «новизну» — одним проходом по обзвонной CSV (161761 юрлицо).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'C:\sender\server')

import enrich_contacts as EC   # noqa: E402
import enrich_db               # noqa: E402

ИСТОЧНИК = 'отзывы-поставщиков'
ТЕХ_РОЛИ = ('гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
            'техдиректор', 'нач.производства', 'нач.цеха', 'АСУ/КИПиА',
            'гл.конструктор')
ПОТОК = r'C:\seostat\drop\reviews_stream.jsonl'


def main():
    db = enrich_db.EnrichDB()
    q = db.cx.execute(
        'SELECT inn,person,post,role,phone,email,source_url,observed_at '
        'FROM people WHERE source=?', (ИСТОЧНИК,)).fetchall()
    люди = [dict(zip(('inn', 'person', 'post', 'role', 'phone', 'email',
                      'url', 'observed_at'), r)) for r in q]
    инны = sorted({p['inn'] for p in люди if p['inn']})
    тех = [p for p in люди if p['role'] in ТЕХ_РОЛИ]
    скон = [p for p in люди if p['phone'] or p['email']]

    комп = {}
    for i in инны:
        r = db.cx.execute(
            'SELECT name,okved,is_competitor FROM companies WHERE inn=?',
            (i,)).fetchone()
        if r:
            комп[i] = {'name': r[0], 'okved': r[1], 'is_competitor': r[2]}

    # НОВИЗНА: один проход по обзвонной базе по короткому списку ИНН
    в_базе = {}
    try:
        в_базе = EC._base_index(set(инны))
    except Exception as e:                              # noqa: BLE001
        print('база недоступна:', type(e).__name__, str(e)[:120], flush=True)
    новых = [i for i in инны if i not in в_базе]

    # свежесть — из потока (в people её нет)
    свеж = {}
    try:
        for s in open(ПОТОК, encoding='utf-8'):
            s = s.strip()
            if not s:
                continue
            z = json.loads(s)
            if z.get('инн'):
                свеж[z['инн'] + '|' + z.get('фио', '')] = z.get('свежесть', '')
    except Exception:                                   # noqa: BLE001
        pass
    расп = {}
    for v in свеж.values():
        k = v.split(' (')[0] or 'нет'
        расп[k] = расп.get(k, 0) + 1

    итог = {'людей_в_базе': len(люди), 'технических': len(тех),
            'предприятий_ИНН': len(инны),
            'новых_для_обзвонной_базы': len(новых),
            'уже_в_обзвонной_базе': len(в_базе),
            'с_контактом': len(скон),
            'конкурентов': sum(1 for c in комп.values() if c['is_competitor']),
            'свежесть': расп}
    print('ЗАМЕР ' + json.dumps(итог, ensure_ascii=False), flush=True)
    print('--- ТЕХНИЧЕСКИЕ ---', flush=True)
    for p in тех:
        c = комп.get(p['inn'], {})
        print('  ' + json.dumps(
            {'инн': p['inn'], 'компания': c.get('name'), 'оквэд': c.get('okved'),
             'фио': p['person'], 'должность': p['post'], 'роль': p['role'],
             'тел': p['phone'], 'почта': p['email'], 'url': p['url'],
             'новая': p['inn'] not in в_базе}, ensure_ascii=False), flush=True)
    print('--- ВСЕ ОСТАЛЬНЫЕ ---', flush=True)
    for p in люди:
        if p in тех:
            continue
        c = комп.get(p['inn'], {})
        print('  ' + json.dumps(
            {'инн': p['inn'], 'компания': c.get('name'), 'фио': p['person'],
             'должность': p['post'], 'роль': p['role'],
             'новая': p['inn'] not in в_базе}, ensure_ascii=False), flush=True)
    print('ЗАМЕР2 ' + json.dumps(итог, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
