# -*- coding: utf-8 -*-
"""Фаза 3.3. Марка/модель машины из цитат фактов: словарь марок парка (PARK-SLOVAR-MAROK-2S.csv, 738 марок с написаниями,
подтверждённых 2+ предприятиями) + список брендов. Заполняет fakty.marka_model там, где пусто. Идемпотентно."""
import os, sys, re, csv, sqlite3
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
csv.field_size_limit(10**8)
BRENDY = ['Atlas Copco', 'Атлас Копко', 'Remeza', 'Ремеза', 'Dalgakiran', 'Далгакыран', 'Kaeser', 'Ingersoll Rand', 'Ингерсолл', 'ABAC', 'Fini', 'Ceccato', 'Berg', 'КЭМП', 'Fiac', 'Chicago Pneumatic',
          'Boge', 'Ekomak', 'Comprag', 'Airpol', 'Mattei', 'Hertz', 'Kraftmann', 'Zammer', 'Almig', 'Alup', 'Gardner Denver', 'Quincy', 'Sullair', 'Elgi', 'Fusheng', 'Mark', 'Rotorcomp', 'Beko',
          'Donaldson', 'Parker', 'Hankison', 'Omi', 'Friulair', 'Airtek', 'Бежецкий', 'Пензкомпрессормаш', 'Казанькомпрессормаш', 'Уралкомпрессормаш', 'Челябинский компрессорный', 'Compair', 'CompAir',
          'Bitzer', 'Copeland', 'Danfoss', 'Embraco', 'Frascold', 'Bock', 'Sauer', 'Bauer', 'Coltri', 'Nardi', 'Denyo', 'Airman', 'Doosan', 'Sullair', 'Ariel', 'Siemens', 'Dresser', 'Cooper']
BR = re.compile(r'\b(' + '|'.join(re.escape(b) for b in BRENDY) + r')\b', re.I)
MODEL = re.compile(r'\b([А-ЯA-Z]{1,6}[- ]?\d{1,4}(?:[-/,.]\d{1,4}){0,3}(?:[- ]?[А-ЯA-Z]{1,4}\d{0,3})?)\b')
slovar = []
p = os.path.join(AK, 'PARK-SLOVAR-MAROK-2S.csv')
if os.path.exists(p):
    for r in csv.DictReader(open(p, encoding='utf-8-sig', newline=''), delimiter=';'):
        naps = [x.strip() for x in (r.get('napisaniya') or '').split('|') if x.strip()]
        if r.get('marka'): slovar.append((r['marka'], r.get('tip', ''), [re.compile(r'(?<![\w-])' + re.escape(n) + r'(?![\w])', re.I) for n in naps]))
c = sqlite3.connect(DB, timeout=120); n_sl = n_br = n_md = 0
rows = c.execute("select id, citata, tip from fakty where (marka_model is null or marka_model='') and citata is not null").fetchall()
for fid, cit, tip in rows:
    m = ''
    for marka, t, rxs in slovar:
        if any(rx.search(cit) for rx in rxs): m = marka; n_sl += 1; break
    if not m:
        b = BR.search(cit)
        if b:
            md = MODEL.search(cit[b.end():b.end() + 60]); m = b.group(1) + (' ' + md.group(1) if md else ''); n_br += 1
    if not m and re.search(r'компрессор|воздуходув|ресивер|осушител', cit, re.I):
        md = re.search(r'(?:компрессор\w*|воздуходувк\w*|ресивер\w*|воздухосборник\w*|осушител\w*|установк\w*)\s+(?:[а-яё]+\s+){0,2}([А-ЯA-Z]{1,6}[- ]?\d{1,4}(?:[-/,.]\d{1,4}){0,3}(?:[- ]?[А-ЯA-Z]{1,4}\d{0,3})?)', cit)
        if md: m = md.group(1); n_md += 1
    if m: c.execute('update fakty set marka_model=? where id=?', (m[:80], fid))
c.commit()
print(f'фактов без марки было {len(rows)}: по словарю {n_sl}, по бренду {n_br}, по шаблону модели {n_md} | с маркой всего', c.execute("select count(*), count(distinct inn) from fakty where marka_model!='' and marka_model is not null").fetchone())
print('топ марок:', c.execute("select marka_model, count(*) from fakty where marka_model!='' group by 1 order by 2 desc limit 15").fetchall())
c.close()
