import sys, json, re, pandas as pd
p, b1 = sys.argv[1], sys.argv[2]
x = pd.ExcelFile(p)
sv = x.parse('Сводка')
print('=== СВОДКА')
for _, r in sv.iterrows():
    print(' -', str(r.iloc[0])[:400], '|', '' if pd.isna(r.iloc[1]) else r.iloc[1])
k = x.parse('Компании', dtype={'ИНН': str})
c = x.parse('Контакты', dtype={'ИНН': str})
k['ИНН'] = k['ИНН'].str.strip(); c['ИНН'] = c['ИНН'].str.strip()
# база 1
try:
    j = json.load(open(b1, encoding='utf-8'))
    inn1 = set()
    def walk(o):
        if isinstance(o, dict):
            for kk, v in o.items():
                if kk.lower() == 'inn' and v: inn1.add(str(v).strip())
                else: walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(j)
except Exception as e:
    inn1 = set(); print('база1 не прочитана', e)
print('\nИНН в базе 1 (панель):', len(inn1), 'пересечение с файлом 6:', len(inn1 & set(k['ИНН'])))
print('\n=== КОМПАНИИ: перекрёстные')
k['lpr'] = k['Из них ЛПР Meyer'].fillna(0).astype(int)
k['mob'] = k['Мобильных'].fillna(0).astype(int)
k['nom'] = k['Номеров'].fillna(0).astype(int)
k['bx'] = k['Есть контакт в Битрикс'].notna()
k['vyr'] = pd.to_numeric(k['Выручка, руб'], errors='coerce')
print(pd.crosstab(k['lpr'] > 0, k['mob'] > 0, margins=True, rownames=['ЛПР Meyer>0'], colnames=['мобильных>0']))
print(pd.crosstab(k['Сегмент'], [k['lpr'] > 0], margins=True))
print(pd.crosstab(k['Раздел'], k['lpr'] > 0, margins=True))
print(pd.crosstab(k['Есть в файлах Meyer'].fillna('нет'), k['lpr'] > 0, margins=True))
print(pd.crosstab(k['Есть в нашей базе'], k['lpr'] > 0, margins=True))
print('битрикс среди ЛПР>0:', int((k['bx'] & (k['lpr'] > 0)).sum()), 'среди mob>0:', int((k['bx'] & (k['mob'] > 0)).sum()))
print('выручка (млн) квантили, все:', (k['vyr'] / 1e6).quantile([.1, .25, .5, .75, .9]).round(0).to_dict())
print('выручка (млн) квантили, ЛПР>0:', (k[k['lpr'] > 0]['vyr'] / 1e6).quantile([.1, .25, .5, .75, .9]).round(0).to_dict())
print('без выручки среди ЛПР>0:', int(k[k['lpr'] > 0]['vyr'].isna().sum()))
print('Сайт: чей (верх):'); print(k['Сайт: чей'].str.split(':').str[0].value_counts().head(8).to_string())
print('\n=== КОНТАКТЫ')
c['lprm'] = c['ЛПР Meyer'].eq('да')
c['mob'] = c['Мобильный'].notna()
c['dob'] = c['Добавочный'].notna()
print(pd.crosstab(c['Роль'], [c['lprm'], c['mob']], margins=True).to_string())
print(pd.crosstab(c['Источник'], c['lprm'], margins=True).to_string())
print('ЛПР Meyer: с ФИО', int((c['lprm'] & c['ФИО'].notna()).sum()), 'из', int(c['lprm'].sum()),
      '| мобильный', int((c['lprm'] & c['mob']).sum()), '| рабочий с доб.', int((c['lprm'] & ~c['mob'] & c['dob']).sum()),
      '| рабочий без доб.', int((c['lprm'] & ~c['mob'] & ~c['dob']).sum()))
# уровни компаний
lvl = c.groupby('ИНН').apply(lambda g: pd.Series({
    'lpr_mob': int((g['lprm'] & g['mob']).sum()),
    'lpr_dob': int((g['lprm'] & ~g['mob'] & g['dob']).sum()),
    'lpr_rab': int((g['lprm'] & ~g['mob'] & ~g['dob']).sum()),
    'mob_bez_roli': int((~g['lprm'] & g['mob'] & g['Роль'].isin(['без подписи'])).sum()),
    'mob_vse': int(g['mob'].sum()),
    'fio_lpr': int((g['lprm'] & g['ФИО'].notna()).sum()),
}), include_groups=False)
k2 = k.merge(lvl, left_on='ИНН', right_index=True, how='left').fillna({'lpr_mob': 0, 'lpr_dob': 0, 'lpr_rab': 0, 'mob_bez_roli': 0, 'mob_vse': 0, 'fio_lpr': 0})
def uroven(r):
    if r['lpr_mob'] > 0: return '1 ЛПР мобильный'
    if r['lpr_dob'] > 0: return '2 ЛПР рабочий+доб'
    if r['lpr_rab'] > 0: return '3 ЛПР рабочий'
    if r['mob_bez_roli'] > 0: return '4 мобильный без подписи'
    if r['mob_vse'] > 0: return '5 мобильный другой роли'
    if r['nom'] > 0: return '6 только общие/рабочие'
    return '7 без номеров'
k2['uroven'] = k2.apply(uroven, axis=1)
print('\n=== УРОВНИ КОМПАНИЙ')
print(pd.crosstab(k2['uroven'], k2['Сегмент'], margins=True).to_string())
print(pd.crosstab(k2['uroven'], k2['Раздел'], margins=True).to_string())
print(pd.crosstab(k2['uroven'], k2['bx'], margins=True).to_string())
print('накопительно:', k2['uroven'].value_counts().sort_index().cumsum().to_dict())
k2.to_pickle(sys.argv[3])
