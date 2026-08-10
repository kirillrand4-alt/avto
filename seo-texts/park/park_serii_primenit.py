# -*- coding: utf-8 -*-
"""Применяем разбор «марка или позиция» (park_serii_fix.jsonl) и заодно чиним
накопленные повторы в chem_rang.

Что делаем:
  1. 40 фактов, где настоящая марка видна в тексте -> model := марка,
     из chem_rang убираем сегмент «C: серия <позиция>», дописываем «C-испр: …».
  2. 43 факта, где марки в тексте нет -> model := '' (позиция моделью не является),
     сегмент «C: серия …» убираем. Если ранг держался ТОЛЬКО на серии — опускаем
     до E (2), потому что честно известен только тип.
  3. park_rang.py дописывает к chem_rang через ||' | '||, и от повторных запусков
     там накопились одинаковые сегменты по 2-4 раза. Схлопываем, сохраняя порядок.

Старые значения кладём в таблицу pravka_model — чтобы правку можно было проверить и
откатить, а не верить на слово.
"""
import sqlite3, json, os, re

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS pravka_model(
  fakt_id INTEGER, bylo_model TEXT, stalo_model TEXT,
  bylo_chem_rang TEXT, stalo_chem_rang TEXT,
  bylo_rang REAL, stalo_rang REAL, pochemu TEXT, kto TEXT, ts TEXT);
""")


def bez_serii(chem, poz):
    """убираем сегменты «C: серия <позиция>…», сравнивая по буквам-цифрам"""
    n = lambda s: re.sub(r'[^A-Za-zА-Яа-я0-9]', '', (s or '')).upper().replace('Ё', 'Е')
    np = n(poz)
    ost = []
    for seg in (chem or '').split(' | '):
        s = seg.strip()
        if s.startswith('C: серия'):
            # «C: серия ЦК-4 (центробежный)» / «C: серия ЦК4, ветка компрессоры…»
            m = re.match(r'C: серия\s+([^,(]+)', s)
            if m and n(m.group(1)) == np:
                continue
        ost.append(s)
    return ost


def shlopnut(segs):
    vid, out = set(), []
    for s in segs:
        k = re.sub(r'\s+', ' ', s.strip())
        if k and k not in vid:
            vid.add(k)
            out.append(k)
    return ' | '.join(out)


dan = [json.loads(l) for l in open(os.path.join(D, 'park_serii_fix.jsonl'), encoding='utf-8')]
net = [d for d in dan if str(d.get('model_verno', '')).upper().startswith('НЕТ')]
ispr = pochishcheno = ponizheno = 0
for d in net:
    fid = d['id']
    row = cur.execute('select model, chem_rang, rang_mashiny, tip from fakt where id=?',
                      (fid,)).fetchone()
    if not row:
        continue
    bylo_m, bylo_c, bylo_r, tip = row
    poz = (d.get('pozicia') or bylo_m or '').strip()
    nast = (d.get('model_nastoyashchaya') or '').strip()
    segs = bez_serii(bylo_c, poz)
    tolko_seriya = len(segs) < len((bylo_c or '').split(' | '))
    if nast:
        stalo_m = nast
        segs.append('C-испр: марка %s (в тексте), а %s — позиция в цехе' % (nast, poz))
        ispr += 1
    else:
        stalo_m = ''
        segs.append('позиция %s моделью не является (марки в тексте нет)' % poz)
        pochishcheno += 1
    stalo_c = shlopnut(segs)
    stalo_r = bylo_r
    # ранг держался только на серии и другого признака не осталось -> честное E
    if (not nast and tolko_seriya
            and not any(s.startswith(('A:', 'B:', 'D+:')) for s in segs)
            and (bylo_r or 0) > 2 and tip and tip != 'НЕ НАША МАШИНА'):
        stalo_r = 2
        if 'E: известен только тип' not in stalo_c:
            stalo_c += ' | E: известен только тип'
        ponizheno += 1
    cur.execute('insert into pravka_model values (?,?,?,?,?,?,?,?,?,datetime("now"))',
                (fid, bylo_m, stalo_m, bylo_c, stalo_c, bylo_r, stalo_r,
                 (d.get('pochemu') or '')[:200], 'разбор марка/позиция после замечания 3-й'))
    cur.execute('update fakt set model=?, chem_rang=?, rang_mashiny=? where id=?',
                (stalo_m, stalo_c, stalo_r, fid))
p.commit()
print('позиция вместо марки: %d | марка восстановлена: %d | model очищена: %d | ранг опущен до E: %d'
      % (len(net), ispr, pochishcheno, ponizheno))

# ---- 3. схлопываем повторы сегментов по всей таблице ------------------------
n = 0
for fid, chem in cur.execute("select id, chem_rang from fakt where chem_rang like '%|%'").fetchall():
    st = shlopnut(chem.split(' | '))
    if st != chem:
        cur.execute('update fakt set chem_rang=? where id=?', (st, fid))
        n += 1
p.commit()
print('фактов, где chem_rang содержал повторы одного признака:', n)

print('\n=== ПОСЛЕ ПРАВКИ ===')
for q, t in [("select count(*) from fakt", 'фактов'),
             ("select count(*) from fakt where v_parke=1", 'в парке'),
             ("select count(*) from fakt where coalesce(model,'')<>''", 'с моделью'),
             ("select count(*) from fakt where rang_mashiny is not null", 'с рангом'),
             ("select count(*) from pravka_model", 'записей в журнале правок')]:
    print('  %-28s %s' % (t, cur.execute(q).fetchone()[0]))
p.close()
