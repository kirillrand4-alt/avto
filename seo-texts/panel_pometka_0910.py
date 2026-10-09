# -*- coding: utf-8 -*-
"""Пометка «нецелевая» по решению владельца 09.10: Арт Холод (опт продуктами, 46.39) и
племенное свиноводческое хозяйство 7118503160 (01.46.11). Колонка company.pometka_ocheredi
(завёл fixE1); прежнее значение – в журнале на дропе. Балл очереди пересчитывается отдельно
(`fixF2_ball.py --tolko-ball`): компании с пометкой уходят в конец очереди своего продавца.
Без ключа – сухой прогон, `--zapis` – запись."""
import io, json, os, sqlite3, sys, time
KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'
POMETKI = {
    '7704373844': 'нецелевая: 46.39, оптовая торговля продуктами без своего производства (решение владельца 09.10)',
    '7118503160': 'нецелевая: 01.46.11, разведение свиней, племенное хозяйство (решение владельца 09.10)',
}
k = sqlite3.connect(KAT, timeout=60)
k.row_factory = sqlite3.Row
zh = []
for inn, tekst in POMETKI.items():
    r = k.execute('select inn, predpriyatie, okved, pometka_ocheredi from company where inn=?', (inn,)).fetchone()
    if not r:
        print('нет в каталоге:', inn)
        continue
    zh.append({'inn': inn, 'imya': r['predpriyatie'], 'okved': r['okved'], 'bylo': r['pometka_ocheredi'], 'stalo': tekst})
    print(inn, r['predpriyatie'], r['okved'], '|', r['pometka_ocheredi'], '->', tekst)
if '--zapis' in sys.argv:
    with k:
        for z in zh:
            k.execute('update company set pometka_ocheredi=? where inn=?', (z['stalo'], z['inn']))
    put = os.path.join(DROP, time.strftime('panel-pometka-0910-%Y%m%d-%H%M%S.json'))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=1))
    print('записано, журнал', os.path.basename(put))
vse = k.execute("select pometka_ocheredi from company where coalesce(pometka_ocheredi,'')<>''").fetchall()
print('пометок всего: %d (нецелевых %d, недействующих %d)' % (len(vse), sum(1 for x in vse if x[0].startswith('нецелев')),
                                                              sum(1 for x in vse if x[0].startswith('недейств'))))
