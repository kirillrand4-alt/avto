# -*- coding: utf-8 -*-
"""Т2.2. Перечень объектов ОПО по ИНН (monitor-pb) для предприятий края, у которых уже есть факт ЭПБ/закупки.
Обёртка над park_opo_po_inn.po_inn (модуль рядом). Резюм по ИНН в opo-po-inn.jsonl. Факты: vid 'ОПО', ссылка = запись реестра. argv: [бюджет] [TEST]."""
import os, sys, re, json, time, sqlite3
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); sys.path.insert(0, AK)
import park_opo_po_inn as O
F = os.path.join(AK, 'opo-po-inn.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
c = sqlite3.connect(DB, timeout=120)
kandidaty = [r[0] for r in c.execute("select distinct inn from fakty where inn like '22%' and vid_fakta in ('ЭПБ','закупка машины','закупка ТО','закупка запчастей','вакансия') order by inn")]
gotovo = {}
if os.path.exists(F):
    for l in open(F, encoding='utf-8'):
        try: d = json.loads(l); gotovo[d['inn']] = d
        except Exception: pass
ochered = [i for i in kandidaty if i not in gotovo]
if TEST: ochered = ochered[:2]
print(f'кандидатов {len(kandidaty)}, готово {len(gotovo)}, в очереди {len(ochered)}', flush=True)
f = open(F, 'a', encoding='utf-8'); n = 0
for inn in ochered:
    if time.time() - T0 > BUDGET: break
    try:
        obekty = O.po_inn(inn, stranic=4, kart=10, stop_posle=8)
        if isinstance(obekty, tuple): obekty = obekty[0]
        d = {'inn': inn, 'obekty': [ {k: o.get(k) for k in ('naimenovanie_obekta', 'klass_opasnosti', 'reg_nomer', 'ssylka', 'citata', 'data', 'kanal')} for o in (obekty or [])], 'err': ''}
    except Exception as e:
        d = {'inn': inn, 'obekty': [], 'err': repr(e)[:120]}
    f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush(); gotovo[inn] = d; n += 1
f.close()
MASH = re.compile(r'компрессор|воздуходув|воздухоразделительн|азотн|кислородн|сжат\w+ воздух|пневм', re.I)
n_f = 0
for inn, d in gotovo.items():
    for o in d.get('obekty') or []:
        nm = o.get('naimenovanie_obekta') or ''
        if not o.get('ssylka'): continue
        tip = 'компрессорная станция' if MASH.search(nm) else 'ОПО (иное)'
        sila = 5 if MASH.search(nm) else 1
        cit = (nm + ' | класс ' + (o.get('klass_opasnosti') or '') + ' | рег.№ ' + (o.get('reg_nomer') or '') + ' | ' + (o.get('citata') or '')[:250])[:500]
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (inn, None, 'ОПО', tip, o.get('reg_nomer') or '', '', o.get('data') or '', '', '', sila, 'monitor-pb.ru', o['ssylka'], cit, 'ak_opo', TS, f'{inn}|{o["ssylka"]}|{tip}|{o.get("reg_nomer") or ""}|{cit[:80]}')); n_f += 1
c.commit()
n_opo = c.execute("select count(*) from fakty where kto_sobral='ak_opo'").fetchone()[0]
print(f'за заход ИНН {n}; объектов-кандидатов {n_f}; фактов ОПО ak_opo: {n_opo}', flush=True)
c.close()
if not TEST and not [i for i in kandidaty if i not in gotovo]: print('ГОТОВО')
