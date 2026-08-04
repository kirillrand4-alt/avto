# -*- coding: utf-8 -*-
"""Показать ФАКТИЧЕСКУЮ форму записей в потоках. Не угадывать имена полей — смотреть.

Пятый раз за смену я угадала имя поля и получила честный ноль: `title/passage` вместо
`tekst`, `args` вместо `argv`, `returncode` вместо `rc`, `naydeno` вместо `kontakty`.
Каждый раз ошибка выглядела как пустой, но успешный результат — rc=0 и «обработано N».
Поэтому сперва прибор, который печатает ключи, и только потом код, который их читает.

Прибор смотрит ВСЕ списочные поля верхнего уровня, а не то, которое я ожидаю увидеть:
именно ожидание и было ошибкой.
"""
import collections
import glob
import json
import os

for put in sorted(glob.glob(r'C:\sender\_ops\p25-*.jsonl')):
    verh = collections.Counter()
    spiski = collections.defaultdict(collections.Counter)
    primery, vsego = {}, 0
    for ln in open(put, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        vsego += 1
        verh.update(z.keys())
        for k, v in z.items():
            if isinstance(v, list) and v:
                for el in v:
                    if isinstance(el, dict):
                        spiski[k].update(el.keys())
                        primery.setdefault(k, el)
                    else:
                        spiski[k]['<%s>' % type(el).__name__] += 1
    print('=== %s  строк %d, %d КБ' % (os.path.basename(put), vsego,
                                       os.path.getsize(put) // 1024))
    print('    верх: %s' % ', '.join('%s(%d)' % kv for kv in verh.most_common()))
    for k, c in spiski.items():
        print('    [%s] ключи: %s' % (k, ', '.join('%s(%d)' % kv for kv in c.most_common())))
        if k in primery:
            print('        пример: %s' % json.dumps(
                {kk: str(vv)[:70] for kk, vv in primery[k].items()},
                ensure_ascii=False)[:700])
