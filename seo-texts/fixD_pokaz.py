# -*- coding: utf-8 -*-
"""fixD: показать доказательства по паре «компания – домен» для ручной проверки «чей сайт»:
окрестности чужих ИНН/ОГРН, юрназваний, телефонов-источников на скачанных страницах.

    python3 fixD_pokaz.py <папка-fixD> <ИНН> [домен] [--shire 160]
"""
import json
import os
import re
import sys

sys.argv, argv = sys.argv[:1], sys.argv[1:]
D = argv[0]
sys.argv += [os.path.join(D, 'db/meyer_baza1.db'), os.path.join(D, 'pages'), os.path.join(D, 'svyazi.json'),
             os.path.join(D, 'dl/checko-meyer-razbor.json'), '/dev/null']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixD_chey_sayt as C  # noqa: E402

chey = json.load(open(os.path.join(D, 'chey.json'), encoding='utf-8'))
inn = argv[1]
dom = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else None
SH = int(argv[argv.index('--shire') + 1]) if '--shire' in argv else 160
x = chey[inn]
r = C.razbor.get(inn) or {}
print('%s %s | регион %s | юрадрес %s | рук %s | checko-сайты %s' % (inn, x['nazvanie'], x['region'], r.get('adres'),
                                                                      r.get('ruk_fio'), r.get('sayty')))
z = C.svyazi.get(inn) or {}
print('   ОКВЭД %s | УК %s | учр %s' % (z.get('okved_osn'), [u['naim'] for u in z.get('uk', [])],
                                    [(u['naim'][:50], u['dolya']) for u in z.get('uchrediteli', [])][:4]))
for d, v in x['domeny'].items():
    if dom and d != dom:
        continue
    print('== %s: %s | свой %s | гр %s | чуж %s | косв %s' % (d, v['verdikt'], v['svoj'], v['gruppa'], v['chuzhoy'], v['kosv']))
    print('   юрназвания: %s' % v['urnazv'])
    for u in C.stranicy_domena(d):
        t = C.tekst_stranicy(u)
        print('   -- %s (%d зн.) %s' % (u, len(t), t[:SH].replace('\n', ' ')))
        for m in re.finditer(r'ИНН|ОГРН', t):
            print('      [%s]' % t[max(0, m.start() - SH):m.start() + 60])
            break
    for kid in v['kontakty'][:6]:
        import sqlite3
        k = sqlite3.connect(os.path.join(D, 'db/meyer_baza1.db'))
        row = k.execute('select value, person, position, role, source_url, substr(coalesce(fragment,""),1,200) from contact where id=?', (kid,)).fetchone()
        print('   контакт %s: %s' % (kid, row))
