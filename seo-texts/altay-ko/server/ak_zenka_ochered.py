# -*- coding: utf-8 -*-
"""Задание 1 для зенки: дописать в ochered.txt сайты предприятий края (ИНН;URL;oba) для обхода существующим кубиком.
Берём тех, у кого есть сайт и класс доказано/косвенно/кандидат, кого ещё нет в очереди и в gotovo. argv: [сколько]."""
import os, sys, re, sqlite3, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
OB = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
OCH = os.path.join(OB, 'ochered.txt'); GOT = os.path.join(OB, 'gotovo'); OTD = os.path.join(OB, 'otdano.txt')
PREDEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
est = set()
for p in (OCH, OTD):
    if os.path.exists(p):
        for l in open(p, encoding='utf-8', errors='replace'):
            i = l.split(';')[0].strip()
            if i.isdigit(): est.add(i)
if os.path.isdir(GOT):
    for f in os.listdir(GOT):
        m = re.match(r'(\d{10,12})', f)
        if m: est.add(m.group(1))
print('в очереди/отдано/готово уже', len(est), 'ИНН')
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
vyr = {r[0]: (r[1] or 0) for r in c.execute('select inn, max(vyruchka_rub) from finansy group by 1')}
rows = c.execute("""select inn, sayt, klass from predpriyatiya where sayt is not null and sayt!='' and inn like '22%'
                    and (klass like 'доказано%' or klass like 'косвенно%' or klass like 'кандидат%')""").fetchall()
c.close()
por = {'доказано': 0, 'доказано (слабо)': 1, 'косвенно': 2}
kand = sorted([r for r in rows if r[0] not in est], key=lambda r: (por.get(r[2], 3), -vyr.get(r[0], 0)))
print('кандидатов на обход', len(kand), 'из', len(rows), 'с сайтом')
n = 0
with open(OCH, 'a', encoding='utf-8') as f:
    for inn, sayt, kl in kand[:PREDEL]:
        u = sayt.strip()
        if not u.startswith('http'): u = 'http://' + u
        f.write(f'{inn};{u};oba\n'); n += 1
print('дописано в ochered.txt', n, '| файл', OCH, os.path.getsize(OCH), 'байт')
