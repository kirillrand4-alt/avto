# -*- coding: utf-8 -*-
"""Сведение карточек из старых выгрузок реестра ЭПБ (2019-2023) с юрлицами края по названию.
В тех файлах нет ни субъекта РФ, ни ИНН, поэтому регион определяем так: нормализуем название
эксплуатанта и ищем его среди юрлиц Алтайского края. Защита от однофамильцев: привязываем только
если в крае ровно ОДНО юрлицо с таким названием и название достаточно длинное. Такой карточке
ставим силу 4 (не 5): заключение подлинное, но принадлежность выведена по имени, а не по ИНН.
argv: [POKAZAT] - разобрать и показать, в базу не писать."""
import os, re, sys, json, time, sqlite3, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
POKAZAT = 'POKAZAT' in sys.argv
SSYLKA = 'https://zsib.gosnadzor.ru/activity/ekspert/svedeniya-iz-reestra/'
TS = time.strftime('%Y-%m-%d %H:%M')

FORMY = re.compile(r'\b(общество\s+с\s+ограниченной\s+ответственностью|акционерное\s+общество|публичное|непубличное|открытое|закрытое|'
                   r'федеральное\s+(казенное|государственное|бюджетное)\s+\w+|государственное\s+унитарное\s+предприятие|'
                   r'муниципальное\s+(унитарное|бюджетное|казенное)\s+\w+|унитарное\s+предприятие|'
                   r'ооо|оао|зао|пао|ао|нао|фкп|фгуп|гуп|муп|мбу|мку|кгбуз|кгку|кгуп|ип)\b', re.I)
def norm(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[«»"\'`]', ' ', s)
    s = FORMY.sub(' ', s)
    s = re.sub(r'[^а-яa-z0-9]+', '', s)
    return s

c = sqlite3.connect(DB, timeout=180)
# карта названий края: имя -> множество ИНН (если ИНН больше одного, привязку не делаем)
karta = collections.defaultdict(set)
for inn, nz, nzp in c.execute("select inn, nazvanie, nazvanie_polnoe from predpriyatiya where inn like '22%' or adres like '%Алтайский край%'"):
    for x in (nz, nzp):
        n = norm(x)
        if len(n) >= 8: karta[n].add(inn)
print('названий края в карте:', len(karta))

kart = json.load(open(os.path.join(AK, 'kartochki-rtn.json'), encoding='utf-8'))
est = {r[0] for r in c.execute('select inn from predpriyatiya')}
bylo = c.execute('select count(*) from fakty').fetchone()[0]
sch = collections.Counter(); privyazano = set(); ne_nashli = collections.Counter()
for k in kart:
    inn = k.get('inn') or ''
    sila = 5
    if not inn:
        varianty = set()
        for imya in (k.get('imya'), k.get('zayavitel')):
            n = norm(imya)
            if len(n) >= 8 and n in karta: varianty |= karta[n]
        if len(varianty) != 1:
            sch['не привязано' if not varianty else 'тёзки в крае'] += 1
            if not varianty: ne_nashli[(k.get('imya') or '')[:60]] += 1
            continue
        inn = varianty.pop(); sila = 4
    if inn not in est:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochnik_klassa) values(?,?,?)', (inn, k.get('imya'), 'реестр РТН'))
        est.add(inn); sch['новых предприятий'] += 1
    pom = '' if sila == 5 else ' | привязка по названию организации, ИНН в выгрузке не указан'
    kl = f'{inn}|{k.get("reg")}|{k["tip"]}||{k["citata"][:80]}'
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, k.get('imya'), k.get('vid_fakta') or 'ЭПБ', k['tip'], '', '', k.get('data'), k.get('srok_do'), '', sila,
               'zsib.gosnadzor.ru', SSYLKA, (k['citata'] + pom)[:600], 'ak_rtn', TS, kl))
    privyazano.add(inn); sch['карточек привязано'] += 1
if POKAZAT: c.rollback()
else: c.commit()
stalo = c.execute('select count(*) from fakty').fetchone()[0]
print('карточек в файле', len(kart), '| привязано', sch['карточек привязано'], '| предприятий', len(privyazano))
print('не нашлось в крае:', sch['не привязано'], '| тёзки (пропущены):', sch['тёзки в крае'], '| новых предприятий:', sch['новых предприятий'])
print('прибавка карточек в базе:', stalo - bylo)
print('частые не найденные (это соседние регионы округа):', [f'{n}×{v}' for n, v in ne_nashli.most_common(5)])
print('ИНН с ЭПБ:', c.execute("select count(distinct inn) from fakty where vid_fakta='ЭПБ'").fetchone()[0])
c.close()
