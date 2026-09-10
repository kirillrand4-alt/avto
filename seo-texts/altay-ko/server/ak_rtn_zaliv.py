# -*- coding: utf-8 -*-
"""Заливка карточек из годовых выгрузок реестра ЭПБ Ростехнадзора (kartochki-rtn.json) в AK-BAZA.
Источник - официальный сайт территориального управления, поэтому сила 5, как у обхода реестра.
Ссылка ведёт на раздел выгрузок; проверяется по регистрационному номеру заключения в цитате.
Предприятие, которого нет в базе, заводится: реестр Ростехнадзора - достаточное основание."""
import os, sys, json, sqlite3, time, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
SSYLKA = 'https://zsib.gosnadzor.ru/activity/ekspert/svedeniya-iz-reestra/'
TS = time.strftime('%Y-%m-%d %H:%M')
kart = json.load(open(os.path.join(AK, 'kartochki-rtn.json'), encoding='utf-8'))
c = sqlite3.connect(DB, timeout=180)
est = {r[0] for r in c.execute('select inn from predpriyatiya')}
bylo = c.execute('select count(*) from fakty').fetchone()[0]
n_nov_pred = 0; sch = collections.Counter()
for k in kart:
    inn = k['inn']
    if inn not in est:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochnik_klassa) values(?,?,?)', (inn, k.get('imya'), 'реестр РТН'))
        est.add(inn); n_nov_pred += 1
    kl = f'{inn}|{k.get("reg")}|{k["tip"]}||{k["citata"][:80]}'
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, k.get('imya'), 'ЭПБ', k['tip'], '', '', k.get('data'), k.get('srok_do'), '', 5,
               'zsib.gosnadzor.ru', SSYLKA, k['citata'], 'ak_rtn', TS, kl))
    sch[k['tip']] += 1
c.commit()
stalo = c.execute('select count(*) from fakty').fetchone()[0]
print('карточек в файле', len(kart), '| влито новых', stalo - bylo, '| новых предприятий', n_nov_pred)
print('по типам:', dict(sch))
print('ИНН с ЭПБ теперь:', c.execute("select count(distinct inn) from fakty where vid_fakta='ЭПБ'").fetchone()[0])
print('всего карточек:', stalo)
c.close()
