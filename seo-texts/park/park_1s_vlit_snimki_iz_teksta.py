# -*- coding: utf-8 -*-
"""Вливает вердикты съёмки из текста: 53 номера получили настоящий кадр вместо пустого.

Съёмка шла прибором `park_1s_snimok_iz_teksta.py` — он берёт страницу обычной загрузкой (её
отдают) и отрисовывает её текст в браузере (браузеру страницу не отдают ни с сервера, ни из
песочницы). Доказанность ставится только при трёх условиях сразу: номер записан связно,
фамилия стоит рядом, страница связана с предприятием.
"""
import json, os, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
bylo = c.execute('select count(*) from nomer_dokaz where dokazano=1').fetchone()[0]
itog = {'доказано': 0, 'не доказано': 0, 'строки в базе не нашлось': 0}
for ln in open(os.path.join(D, 'park_nomera_iz_teksta.jsonl'), encoding='utf-8'):
    if not ln.strip():
        continue
    r = json.loads(ln)
    dok = 1 if (r.get('vyvod') or '').startswith('ДОКАЗАНО') else 0
    cifry = ''.join(ch for ch in (r.get('nomer') or '') if ch.isdigit())[-10:]
    est = c.execute('select 1 from nomer_dokaz where inn=? and nomer like ?',
                    (r['inn'], '%' + cifry)).fetchone()
    if not est:
        itog['строки в базе не нашлось'] += 1
        continue
    itog['доказано' if dok else 'не доказано'] += 1
    if PISAT:
        c.execute("""update nomer_dokaz set dokazano=?, snimok=?, vyvod=?, citata=?, svyaz=?
                      where inn=? and nomer like ?""",
                  (dok, r.get('snimok') or '', r.get('vyvod') or '', (r.get('citata') or '')[:600],
                   r.get('svyaz') or '', r['inn'], '%' + cifry))
for k, v in itog.items():
    print('  %-28s %d' % (k, v))
if not PISAT:
    print('\nсухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback(); p.close(); raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'СНИМКИ ИЗ ТЕКСТА: доказательство номеров',
           sum(itog.values()), itog['доказано'], itog['не доказано'],
           'страница берётся загрузкой, отрисовывается локально, оговорка на кадре'))
p.commit()
print('\nдоказано номеров: было %d, стало %d'
      % (bylo, c.execute('select count(*) from nomer_dokaz where dokazano=1').fetchone()[0]))
print('предприятий с доказанным номером: %d'
      % c.execute('select count(distinct inn) from nomer_dokaz where dokazano=1').fetchone()[0])
p.close()
