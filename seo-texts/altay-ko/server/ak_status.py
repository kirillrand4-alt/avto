# -*- coding: utf-8 -*-
"""Проверка, действует ли предприятие: статус ЕГРЮЛ через DaData по ИНН.
Заодно подтягиваем название, ОГРН, ОКВЭД, адрес и руководителя - у предприятий, пришедших из
реестра Ростехнадзора, кроме ИНН и имени ничего нет. Ключ берём из окружения или из runner-secrets.env
(значение нигде не печатаем). Резюм по ИНН в dadata-status.jsonl. argv: [бюджет_сек] [VSE]."""
import os, re, sys, json, time, sqlite3, collections, warnings
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import requests
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F = os.path.join(AK, 'dadata-status.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1200
VSE = 'VSE' in sys.argv
T0 = time.time()

TOK = os.environ.get('DADATA_TOKEN', '')
if not TOK:
    for p in (os.path.join(AK, 'rs.env'), r'C:\sender\rs.env', r'C:\sender\runner-secrets.env'):
        if os.path.exists(p):
            for l in open(p, encoding='utf-8', errors='replace'):
                if l.strip().startswith('DADATA_TOKEN='): TOK = l.strip().split('=', 1)[1].strip()
            if TOK: break
print('ключ DaData:', 'есть' if TOK else 'НЕТ - обогащение невозможно')
if not TOK: sys.exit(1)
S = requests.Session()
S.headers.update({'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Token ' + TOK})

c = sqlite3.connect(DB, timeout=180)
if VSE:
    kand = [r[0] for r in c.execute("select distinct inn from fakty")]
else:
    kand = [r[0] for r in c.execute("select distinct inn from fakty where vozduh=1")]
gotovo = {}
if os.path.exists(F):
    for l in open(F, encoding='utf-8', errors='replace'):
        try: d = json.loads(l); gotovo[d['inn']] = d
        except Exception: pass
ochered = [i for i in kand if i not in gotovo]
print(f'предприятий {len(kand)}, уже спрошено {len(gotovo)}, в очереди {len(ochered)}')

f = open(F, 'a', encoding='utf-8'); n = 0; sch = collections.Counter()
for inn in ochered:
    if time.time() - T0 > BUDGET: break
    try:
        r = S.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party', json={'query': inn, 'count': 1}, timeout=40)
        js = r.json() if r.status_code == 200 else {}
        sug = (js.get('suggestions') or [None])[0]
    except Exception as e:
        sug = None; sch['сбой: ' + type(e).__name__] += 1
    d = {'inn': inn}
    if sug:
        v = sug.get('data') or {}
        d.update({'nazvanie': (v.get('name') or {}).get('short_with_opf') or sug.get('value'),
                  'polnoe': (v.get('name') or {}).get('full_with_opf'),
                  'ogrn': v.get('ogrn'), 'status': (v.get('state') or {}).get('status'),
                  'likvid': (v.get('state') or {}).get('liquidation_date'),
                  'okved': v.get('okved'), 'adres': ((v.get('address') or {}).get('value')),
                  'ruk': ((v.get('management') or {}).get('name')), 'tip': v.get('type')})
    f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush(); gotovo[inn] = d; n += 1
    sch[d.get('status') or 'не найдено'] += 1
    time.sleep(0.06)
f.close()
print('спрошено за заход', n, '| статусы:', dict(sch))

n_u = 0
for inn, d in gotovo.items():
    if not d.get('status'): continue
    c.execute('''update predpriyatiya set status_egrul=?,
                 nazvanie=coalesce(nullif(nazvanie,''), ?), nazvanie_polnoe=coalesce(nullif(nazvanie_polnoe,''), ?),
                 ogrn=coalesce(nullif(ogrn,''), ?), okved_osn=coalesce(nullif(okved_osn,''), ?),
                 adres=coalesce(nullif(adres,''), ?), rukovoditel=coalesce(nullif(rukovoditel,''), ?)
                 where inn=?''',
              (d['status'], d.get('nazvanie'), d.get('polnoe'), d.get('ogrn'), d.get('okved'), d.get('adres'), d.get('ruk'), inn))
    n_u += 1
c.commit()
print('обновлено записей предприятий:', n_u)
print('статусы у предприятий с воздушным фактом:')
for r in c.execute("select coalesce(nullif(status_egrul,''),'неизвестен'), count(*) from predpriyatiya where inn in (select distinct inn from fakty where vozduh=1) group by 1 order by 2 desc"):
    print('   ', r)
c.close()
if not [i for i in kand if i not in gotovo]: print('ГОТОВО')
