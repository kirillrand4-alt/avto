import sys, json, re, collections, pandas as pd
x = pd.ExcelFile(sys.argv[1])
sv = x.parse('Сводка', header=None)
print('=== СВОДКА')
for _, r in sv.iterrows():
    a = '' if pd.isna(r.iloc[0]) else str(r.iloc[0]); b = '' if pd.isna(r.iloc[1]) else r.iloc[1]
    if a or b: print(' -', a[:230], '|', b)
k = x.parse('Компании', dtype=str); n = x.parse('Номера', dtype=str)
k['ИНН'] = k['ИНН'].str.strip(); n['ИНН'] = n['ИНН'].str.strip()
inn1 = {c['inn'] for c in json.load(open(sys.argv[2], encoding='utf-8'))['kompanii']}
inn6 = {c['inn'] for c in json.load(open(sys.argv[3], encoding='utf-8'))['kompanii']}
k6 = pd.ExcelFile(sys.argv[4]).parse('Компании', dtype=str)['ИНН'].str.strip()
print('\nв панели: Base1 %d, Base6 %d; в файле 6 (весь) %d' % (
    k['ИНН'].isin(inn1).sum(), k['ИНН'].isin(inn6).sum(), k['ИНН'].isin(set(k6)).sum()))
k['vpaneli'] = k['ИНН'].isin(inn1 | inn6)
print('Приоритет × тип контакта:'); print(pd.crosstab(n['Приоритет'], n['Тип контакта']).to_string())
print(pd.crosstab(n['Роль (класс)'].fillna('—'), n['Тип номера']).to_string())
n['lpr'] = n['Тип контакта'].eq('ЛПР по списку')
n['mob'] = n['Тип номера'].eq('мобильный')
n['dob'] = n['Тип номера'].eq('городской + доб.')
lv = n.groupby('ИНН').apply(lambda g: pd.Series({
    'lpr_mob': int((g.lpr & g.mob).sum()), 'lpr_dob': int((g.lpr & g.dob).sum()), 'lpr_rab': int((g.lpr & ~g.mob & ~g.dob).sum()),
    'obsh': int(g['Тип контакта'].eq('общий номер / приёмная').sum()), 'mob': int(g.mob.sum()), 'vsego': len(g),
    'fio_lpr': int((g.lpr & g['ФИО'].notna()).sum()), 'iz_tabl': int(g['Номер из таблицы CC'].eq('да').sum())}), include_groups=False)
k2 = k.merge(lv, left_on='ИНН', right_index=True, how='left').fillna(0)
def ur(r):
    if r.lpr_mob: return '1 ЛПР мобильный'
    if r.lpr_dob: return '2 ЛПР рабочий+доб'
    if r.lpr_rab: return '3 ЛПР рабочий'
    if r.obsh: return '4 есть приёмная/общий'
    if r.mob: return '5 только мобильные без роли'
    if r.vsego: return '6 только рабочие без роли'
    return '7 без номеров'
k2['ur'] = k2.apply(ur, axis=1)
k2['vyr'] = pd.to_numeric(k2['Выручка, руб'], errors='coerce')
print('\nуровни (все / не в панели):')
print(pd.crosstab(k2['ur'], k2['vpaneli'], margins=True).to_string())
print(pd.crosstab(k2['ur'], k2['Сегмент (по таблице)'].str.split(' \\| ').str[0]).to_string())
print('\nОтбор × ЛПР:'); print(pd.crosstab(k2['Отбор'], k2['ur'].str[0]).to_string())
print('Новизна:', k2['Новизна vs старые базы'].value_counts().to_dict())
print('В нашей базе обзвона:', k2['В нашей базе обзвона'].fillna('—').value_counts().to_dict(), '× ЛПР>0:', int(((k2['В нашей базе обзвона'].notna()) & (k2.ur.str[0].astype(int) <= 3)).sum()))
def vyr_bin(v):
    if pd.isna(v) or v == 0: return 'нет/0'
    return '≥1,5 млрд' if v >= 1.5e9 else '300 млн–1,5 млрд' if v >= 3e8 else '<300 млн'
k2['vb'] = k2['vyr'].map(vyr_bin)
print(pd.crosstab(k2['ur'], k2['vb']).to_string())
osn = k2['Основной ОКВЭД'].str[:2]
print('основной ОКВЭД (раздел) у ЛПР-компаний:', osn[k2.ur.str[0].astype(int) <= 3].value_counts().head(10).to_dict())
print('примеры ЛПР-компаний:')
for _, r in k2[k2.ur.str[0].astype(int) <= 3].sort_values('vyr', ascending=False).head(12).iterrows():
    print('   %-34s %-22s %-10s %8s млн %s | %s' % (r['Название'][:34], r['ur'], r['Сегмент (по таблице)'][:10], '%.0f' % (r['vyr']/1e6) if r['vyr']==r['vyr'] else '-', r['Основной ОКВЭД'], str(r['Описание (по сайту)'])[:60]))
k2.to_pickle(sys.argv[5])
