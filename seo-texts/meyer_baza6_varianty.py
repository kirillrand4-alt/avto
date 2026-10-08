import sys, json, pandas as pd
k2 = pd.read_pickle(sys.argv[1])
c = pd.ExcelFile(sys.argv[2]).parse('Контакты', dtype={'ИНН': str}); c['ИНН'] = c['ИНН'].str.strip()
inn1 = set()
def walk(o):
    if isinstance(o, dict):
        for kk, v in o.items():
            if kk.lower() == 'inn' and v: inn1.add(str(v).strip())
            else: walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(json.load(open(sys.argv[3], encoding='utf-8')))
k2['v_baze1'] = k2['ИНН'].isin(inn1)
print('пересечение с Базой 1 по файлам Meyer:', k2[k2['v_baze1']]['Есть в файлах Meyer'].fillna('нет').value_counts().to_dict(), 'уровни:', k2[k2['v_baze1']]['uroven'].value_counts().to_dict())
# общие номера между разными ИНН
c['nom'] = c['Мобильный'].fillna(c['Рабочий']).astype(str).str.replace(r'\D', '', regex=True).str[-10:]
obshch = c.groupby('nom')['ИНН'].nunique()
obshch = set(obshch[obshch > 1].index)
inn_obshch = set(c[c['nom'].isin(obshch)]['ИНН'])
k2['obshch_nomer'] = k2['ИНН'].isin(inn_obshch)
vyr = k2['vyr']
def pokaz(nazv, m):
    d = k2[m & ~k2['v_baze1']]
    print('\n## %s: %d компаний (ещё %d уже в Базе 1)' % (nazv, len(d), int((m & k2['v_baze1']).sum())))
    print('   по уровню:', d['uroven'].value_counts().sort_index().to_dict())
    print('   по сегменту:', d['Сегмент'].value_counts().to_dict())
    print('   выручка ≥1,5 млрд: %d, 300 млн–1,5 млрд: %d, <300 млн: %d, неизвестна: %d' % (
        (d['vyr'] >= 1.5e9).sum(), ((d['vyr'] >= 3e8) & (d['vyr'] < 1.5e9)).sum(), (d['vyr'] < 3e8).sum(), d['vyr'].isna().sum()))
    print('   в файлах Meyer 2–5: %d (%s); в Битриксе КЦ: %d; номер общий с другим ИНН: %d; ЛПР с ФИО: %d; нет в нашей базе: %d' % (
        d['Есть в файлах Meyer'].isin(['файл 2', 'файл 3', 'файл 4', 'файл 5']).sum(),
        d['Есть в файлах Meyer'].fillna('').value_counts().drop('', errors='ignore').to_dict(),
        d['bx'].sum(), d['obshch_nomer'].sum(), (d['fio_lpr'] > 0).sum(), (d['Есть в нашей базе'] == 'нет').sum()))
    print('   сайт чей:', d['Сайт: чей'].str.split(':').str[0].str[:25].value_counts().head(6).to_dict())
u = k2['uroven'].str[0].astype(int)
pokaz('В1: только ЛПР (уровни 1–3)', u <= 3)
pokaz('В2: ЛПР + мобильный без подписи (1–4)', u <= 4)
pokaz('В3: ЛПР + крупные ≥1,5 млрд с общими/рабочими номерами (1–3 + 6 крупные)', (u <= 3) | ((u == 6) & (vyr >= 1.5e9)))
# что за мобильные без подписи: фрагменты
m4 = k2[(u == 4) & ~k2['v_baze1']]['ИНН']
cc = c[c['ИНН'].isin(m4) & c['Мобильный'].notna() & (c['Роль'] == 'без подписи')]
print('\nпримеры фрагментов у «мобильный без подписи»:')
for f in cc['Фрагмент страницы'].dropna().sample(8, random_state=1):
    print('  ·', str(f).replace('\n', ' ')[:150])
print('\nдолжности ЛПР Meyer (верх):', c[c['ЛПР Meyer'].eq('да')]['Должность'].fillna('—').value_counts().head(12).to_dict())
