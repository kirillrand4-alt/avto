# -*- coding: utf-8 -*-
"""Заливка того, что собрано из песочницы: реестр monitor-pb отрезал сервер и весь его прокси-пул,
поэтому ЭПБ и ОПО собирались напрямую из песочницы, а сюда приходят готовыми jsonl.
Файлы забираем с дропа. Гейт тот же, что у серверных прогонов, плюс отсев пневмоколёсных кранов:
слово «пневмо» в них есть, а к сжатому воздуху они отношения не имеют."""
import os, re, sys, json, time, sqlite3, urllib.request, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
TS = time.strftime('%Y-%m-%d %H:%M')
for n, imya_na_drope in (('sbor-epb.jsonl', 'sbor-epb-kopiya.jsonl'), ('sbor-opo.jsonl', 'sbor-opo.jsonl')):
    r = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/' + imya_na_drope, headers={'X-Drop-Token': os.environ['DROP_TOKEN']})
    d = urllib.request.urlopen(r, timeout=600).read()
    open(os.path.join(AK, n), 'wb').write(d)
    print(n, len(d) // 1024, 'КБ забран с дропа')

MASH = re.compile(r'компрессор|воздуходув|нагнетател|турбокомпрессор|ресивер|воздухосборник|осушител|воздухоразделительн|\bВРУ\b'
                  r'|генератор\w*\s+(азота|кислорода)|азотн\w+\s+(станц|установ)|кислородн\w+\s+(станц|установ)|компрессорн', re.I)
NE = re.compile(r'пневмоколёсн|пневмоколесн|кран\s+стрелов|автокран|экскаватор', re.I)  # «пневмо» в кране - не про сжатый воздух
VIDY = [('генератор кислорода', r'кислородн\w*\s*(станц|генератор|установ)|генератор\w*\s*кислород'),
        ('генератор азота', r'азотн\w*\s*(станц|генератор|установ)|генератор\w*\s*азот'),
        ('ВРУ', r'воздухоразделительн|\bВРУ\b'), ('нагнетатель', r'нагнетател'), ('воздуходувка', r'воздуходув'),
        ('осушитель', r'осушител'), ('ресивер', r'ресивер|воздухосборник'),
        ('компрессорная станция', r'компрессорн\w+\s*(станци|установк|цех)|цех\s+компрессорн|участок\s+компрессорн'), ('компрессор', r'компрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]
def vid(s):
    for v, rx in VIDY:
        if rx.search(s or ''): return v
    return ''
SQL = '''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
         values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
c = sqlite3.connect(DB, timeout=180)
bylo = c.execute('select count(*) from fakty').fetchone()[0]
sch = collections.Counter()

for l in open(os.path.join(AK, 'sbor-epb.jsonl'), encoding='utf-8', errors='replace'):
    try: d = json.loads(l)
    except Exception: continue
    for r in d.get('stroki') or []:
        ob = r.get('obekt') or ''
        if not MASH.search(ob) or NE.search(ob): continue
        tip = vid(ob)
        if not tip: continue
        cit = (ob[:400] + ' | ' + (r.get('nomer') or '') + ' | ' + (r.get('ekspertnaya_org') or ''))[:500]
        c.execute(SQL, (d['inn'], r.get('predpriyatie'), 'ЭПБ', tip, '', '', r.get('data'), '', '', 5,
                        'monitor-pb.ru', r.get('ssylka'), cit, 'ak_mpb', TS, f'{d["inn"]}|{r.get("ssylka")}|{tip}||{ob[:80]}'))
        sch['ЭПБ'] += 1

for l in open(os.path.join(AK, 'sbor-opo.jsonl'), encoding='utf-8', errors='replace'):
    try: d = json.loads(l)
    except Exception: continue
    for o in d.get('obekty') or []:
        nm = o.get('naimenovanie_obekta') or ''
        if not o.get('ssylka') or not MASH.search(nm) or NE.search(nm): continue
        cit = (nm + ' | класс ' + (o.get('klass_opasnosti') or '') + ' | рег.№ ' + (o.get('reg_nomer') or '') + ' | ' + (o.get('citata') or '')[:250])[:500]
        c.execute(SQL, (d['inn'], None, 'ОПО', vid(nm) or 'компрессорная станция', o.get('reg_nomer') or '', '', o.get('data') or '', '', '', 5,
                        'monitor-pb.ru', o['ssylka'], cit, 'ak_opo', TS, f'{d["inn"]}|{o["ssylka"]}|{vid(nm)}|{o.get("reg_nomer") or ""}|{cit[:80]}'))
        sch['ОПО'] += 1
c.commit()
stalo = c.execute('select count(*) from fakty').fetchone()[0]
print('кандидатов:', dict(sch), '| новых карточек в базе:', stalo - bylo)
print('ИНН с ЭПБ:', c.execute("select count(distinct inn) from fakty where vid_fakta like 'ЭПБ%'").fetchone()[0],
      '| с ОПО:', c.execute("select count(distinct inn) from fakty where vid_fakta='ОПО'").fetchone()[0])
c.close()
# очереди сервера пополняем тем, что уже спрошено, чтобы не спрашивать дважды
for src, dst in (('sbor-epb.jsonl', 'mpb-po-inn.jsonl'), ('sbor-opo.jsonl', 'opo-po-inn.jsonl')):
    with open(os.path.join(AK, dst), 'a', encoding='utf-8') as f:
        n = 0
        for l in open(os.path.join(AK, src), encoding='utf-8', errors='replace'):
            f.write(l); n += 1
    print(f'{dst}: дописано {n} записей')
