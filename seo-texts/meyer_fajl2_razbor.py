import sys, json, re, collections, pandas as pd
x = pd.ExcelFile(sys.argv[1])
sv = x.parse('Сводка', header=None)
for _, r in sv.iterrows():
    a = '' if pd.isna(r.iloc[0]) else str(r.iloc[0]); b = '' if pd.isna(r.iloc[1]) else r.iloc[1]
    if a or b: print(' -', a[:200], '|', b)
k = x.parse('Компании', dtype=str); c = x.parse('Контакты', dtype=str)
for d in (k, c): d['ИНН'] = d['ИНН'].str.strip()
panel = set()
for p in sys.argv[2:5]:
    panel |= {z['inn'] for z in json.load(open(p, encoding='utf-8'))['kompanii']}
k['vpan'] = k['ИНН'].isin(panel)
print('\nуже в панели: %d из %d' % (k.vpan.sum(), len(k)))
LPR = {'закупки', 'директор/руководитель', 'производство', 'главный инженер', 'главный технолог', 'технолог', 'технический директор', 'качество'}
g = c.groupby('ИНН').apply(lambda d: pd.Series({
    'lpr_rol': int(d['Роль'].isin(LPR).sum()), 'ne_lpr': int((~d['Роль'].isin(LPR)).sum()),
    'sverka_ok': int(d['Сверка'].str.contains('верно|исправлено', na=False).sum()),
    'storon': int(d['Проверка'].fillna('').str.contains('сторон').sum()),
    'fio': int(d['ФИО'].notna().sum()), 'elev': int(d['Тип контакта'].str.contains('элеватор').sum()),
    'roli': ', '.join(sorted(set(d['Роль'])))}), include_groups=False)
k2 = k.merge(g, left_on='ИНН', right_index=True, how='left')
k2['vyr'] = pd.to_numeric(k2['Выручка, руб'], errors='coerce')
nov = k2[~k2.vpan]
print('роли у новых (компаний):', collections.Counter(r for s in nov.roli for r in s.split(', ')).most_common())
print('только не-ЛПР роли (бухгалтерия/продажи…):', int((nov.lpr_rol == 0).sum()), nov[nov.lpr_rol == 0].roli.value_counts().to_dict())
print('номер со стороннего сайта:', int((nov.storon > 0).sum()), '| не сверено ни одного:', int((nov.sverka_ok == 0).sum()))
print('попадание:', nov['Попадание'].value_counts().to_dict())
print('база обзвона:', nov['В какой базе обзвона'].value_counts().to_dict())
def vb(v):
    if v != v: return 'нет'
    return '≥1,5 млрд' if v >= 1.5e9 else '300 млн–1,5 млрд' if v >= 3e8 else '100–300 млн' if v >= 1e8 else '<100 млн'
nov = nov.assign(vb=nov.vyr.map(vb))
print('выручка:', nov.vb.value_counts().to_dict())
print('сегмент:', nov['Сегмент'].value_counts().head(6).to_dict())
print('ОКВЭД основной (раздел):', nov['Основной ОКВЭД'].str[:5].value_counts().head(12).to_dict())
ok = nov[(nov.lpr_rol > 0) & (nov.storon == 0) & (nov.sverka_ok > 0)]
print('\nЛПР-роль + сверено + не сторонний сайт: %d' % len(ok))
print('   + основной ОКВЭД: %d' % (ok['Попадание'] == 'основной ОКВЭД').sum())
for por in (1e8, 3e8):
    m = ok[(ok['Попадание'] == 'основной ОКВЭД') & ((ok.vyr >= por) | ok.vyr.isna())]
    print('   + выручка ≥ %d млн или неизвестна: %d (роли %s)' % (por / 1e6, len(m), collections.Counter(r for s in m.roli for r in s.split(', ') if r in LPR).most_common()))
print('\nпримеры отсева:')
for _, r in nov[(nov.lpr_rol == 0) | (nov.storon > 0) | (nov['Попадание'] != 'основной ОКВЭД')].head(8).iterrows():
    print('   %-32s %-9s %-24s %s | %s' % (r['Название'][:32], vb(r.vyr), r['Попадание'], r.roli[:30], str(r['Описание'])[:50]))
print('\nпримеры отобранных (по выручке):')
for _, r in ok[ok['Попадание'] == 'основной ОКВЭД'].sort_values('vyr', ascending=False).head(8).iterrows():
    print('   %-32s %8s млн %-8s %s | %s' % (r['Название'][:32], '%.0f' % (r.vyr / 1e6) if r.vyr == r.vyr else '-', r['Основной ОКВЭД'], r.roli[:30], str(r['Описание'])[:50]))
k2.to_pickle(sys.argv[5])
