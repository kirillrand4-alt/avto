# -*- coding: utf-8 -*-
"""Почему фильтр не признал компанию нашей: показать её паспорт целиком."""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import nashi  # noqa: E402
import pasport_sverka as PS  # noqa: E402

ИНН = sys.argv[1:] or ['3102046850', '3702268847']
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
sys.stdout.reconfigure(encoding='utf-8')
for inn in ИНН:
    r = c.execute("select coalesce(k.name,'') name, coalesce(k.site,'') site, "
                  "coalesce(f.facts_json,'') f from companies k "
                  "join site_facts f on f.inn=k.inn where k.inn=?", (inn,)).fetchone()
    if not r:
        print(inn, 'нет строки'); continue
    d = json.loads(r['f']) if r['f'] else {}
    t = PS._tekst(inn)
    print('\n=== %s %s (%s) ===' % (inn, r['name'][:45], r['site']))
    for поле in nashi.ПОЛЯ:
        v = d.get(поле)
        сп = v if isinstance(v, list) else ([v] if v else [])
        сп = [str(x) for x in сп if x]
        if not сп:
            continue
        куски = []
        for x in сп[:6]:
            ок = PS._podtverzhdena(x.lower().replace('ё', 'е'), t) if t else None
            метка = ''
            if nashi.ПРЯМО.search(x):
                метка = ' [прямая]'
            elif nashi.ГАЗЫ.search(x):
                метка = ' [газы]'
            elif nashi.КОСВЕННО.search(x):
                метка = ' [косвенная]'
            if nashi.МЕЙЕР.search(x):
                метка += ' [мейер]'
            куски.append('%s%s%s' % (x[:60], метка, '' if ок else ' (НЕ подтв)'))
        print('  %-20s %s' % (поле + ':', ' | '.join(куски)))
    print('  вердикт фильтра:', nashi.разобрать(inn, r['f']))
c.close()
