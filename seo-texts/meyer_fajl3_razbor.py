import sys, json, re, collections, pandas as pd
x = pd.ExcelFile(sys.argv[1])
sv = x.parse('Сводка', header=None)
for _, r in sv.iterrows():
    a = '' if pd.isna(r.iloc[0]) else str(r.iloc[0]); b = '' if pd.isna(r.iloc[1]) else r.iloc[1]
    if a or b: print(' -', a[:220], '|', b)
k = x.parse('Компании', dtype=str); n = x.parse('Номера', dtype=str)
k['ИНН'] = k['ИНН'].str.strip(); n['ИНН'] = n['ИНН'].str.strip()
panel = set()
for p in sys.argv[2:6]:
    panel |= {z['inn'] for z in json.load(open(p, encoding='utf-8'))['kompanii']}
k['vyr'] = pd.to_numeric(k['Выручка, руб'], errors='coerce')
d = k[(k.vyr >= 1e8) & (k.vyr <= 1e9)].copy()
print('\nв диапазоне 100–1000 млн: %d, из них уже в панели %d' % (len(d), d['ИНН'].isin(panel).sum()))
d = d[~d['ИНН'].isin(panel)]
print('попадание:', d['Попадание'].value_counts().to_dict())
print('база обзвона:', d['В какой базе обзвона'].value_counts().to_dict())
print('сегмент:', d['Сегмент'].value_counts().head(10).to_dict())
print('ОКВЭД:', d['Основной ОКВЭД'].value_counts().head(20).to_dict())
print('номеров подтверждено:', d['Номеров подтверждено'].astype(int).describe()[['50%', 'max']].to_dict(),
      collections.Counter(min(int(v), 11) for v in d['Номеров подтверждено']).most_common())
print('есть мобильный:', d['Мобильный'].notna().sum(), 'есть городской:', d['Городской'].notna().sum())
MUSOR = re.compile(r'провер\w* (юр|контраг)|егрюл|егрип|прилинкуйте|хостинг|домен (продается|продаётся)|beget|reg\.ru|справочник|каталог (компаний|предприятий)|агрегатор|тендер|закупк\w* портал|сайт (находится|в разработке)|parking|сервис проверки|интернет-магазин|маркетплейс', re.I)
d['opis'] = d['Описание'].fillna('')
d['musor'] = d.opis.str.contains(MUSOR)
print('описание: нет %d, мусорное %d' % ((d.opis == '').sum(), d.musor.sum()))
print('примеры мусорных:', d[d.musor].opis.str[:80].head(6).tolist())
nn = n[n['ИНН'].isin(set(d['ИНН']))].copy()
nn['c'] = nn['Номер'].str.replace(r'\D', '', regex=True).str[-10:]
shar = n.assign(c=n['Номер'].str.replace(r'\D', '', regex=True).str[-10:]).groupby('c')['ИНН'].nunique()
nn['obshch'] = nn.c.map(shar).fillna(1) > 1
nn['800'] = nn.c.str.startswith('800')
print('номера в диапазоне: %d; тип %s; общие с другими ИНН %d; 8-800 %d; подпись %s; источник %s' % (
    len(nn), nn['Тип номера'].value_counts().to_dict(), nn.obshch.sum(), nn['800'].sum(),
    nn['Подпись в базе'].value_counts().to_dict(), nn['Источник'].value_counts().head(4).to_dict()))
po = nn.groupby('ИНН').apply(lambda g: pd.Series({
    'mob_svoi': int(((g['Тип номера'] == 'мобильный') & ~g.obshch).sum()),
    'gor_svoi': int(((g['Тип номера'] == 'городской') & ~g.obshch & ~g['800']).sum()),
    'vsego': len(g)}), include_groups=False)
d = d.merge(po, left_on='ИНН', right_index=True, how='left').fillna({'mob_svoi': 0, 'gor_svoi': 0, 'vsego': 0})
dobr = d[(d['Попадание'] == 'основной ОКВЭД') & ~d.musor & (d.opis != '') & (d.vsego.between(1, 12)) & ((d.mob_svoi > 0) | (d.gor_svoi > 0))]
print('\nосновной ОКВЭД + нормальное описание + 1–12 номеров + свой (не общий, не 8-800) номер: %d' % len(dobr))
print('   с собственным мобильным: %d' % (dobr.mob_svoi > 0).sum())
print('   сегмент:', dobr['Сегмент'].value_counts().head(8).to_dict())
print('   ОКВЭД (раздел 4 знака):', dobr['Основной ОКВЭД'].str[:5].value_counts().head(15).to_dict())
d.to_pickle(sys.argv[6])
