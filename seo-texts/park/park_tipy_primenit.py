# -*- coding: utf-8 -*-
"""Применение вердиктов полной сверки типов к park.db.

Ось `vid` — новая колонка `vid_fakta`, она отвечает на вопрос «чем это доказывает машину»:
  машина     сама машина            -> в парке, считается в номенклатуре
  узел       часть нашей машины     -> в парке, машину доказывает, но НЕ считается штукой
  расходник  масло/фильтр/ЗИП/ремонт-> в парке, машину доказывает, штукой не считается
  газ        покупает/арендует газ  -> в парке, это ЦЕЛЕВОЙ покупатель генератора
  НЕТ        не наша номенклатура   -> из парка вон (v_parke=0)

Старый тип не затираем молча: он уходит в `pochemu`, чтобы правку можно было оспорить.
"""
import sqlite3, json, os, glob, time, collections

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
if 'vid_fakta' not in [r[1] for r in cur.execute('pragma table_info(fakt)').fetchall()]:
    cur.execute('alter table fakt add column vid_fakta text default ""')
    p.commit()

NASHI = {'компрессор', 'воздуходувка', 'турбокомпрессор', 'нагнетатель', 'ВРУ',
         'генератор азота', 'генератор кислорода', 'МКС', 'ПКС', 'компрессорная станция',
         'ресивер', 'осушитель', 'ГПА'}

verdikty = {}
for f in sorted(glob.glob(os.path.join(D, 'park_tipy_polnyy_*.jsonl'))):
    for ln in open(f, encoding='utf-8'):
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if isinstance(d.get('id'), int):
            verdikty[d['id']] = d          # последний вердикт по id побеждает
print('вердиктов на входе:', len(verdikty))

bylo = {r[0]: (r[1] or '', r[2] or '', r[3]) for r in
        cur.execute('select id, tip, sostoyanie, v_parke from fakt').fetchall()}
print('фактов в базе:', len(bylo))

sch = collections.Counter()
peremeny = collections.Counter()
pravki = []
for fid, d in verdikty.items():
    if fid not in bylo:
        sch['вердикт на несуществующий id'] += 1
        continue
    # модель изредка отвечает латиницей или строчными — приводим, а не выбрасываем
    vid = (d.get('vid') or '').strip()
    vid = {'rashodnik': 'расходник', 'mashina': 'машина', 'uzel': 'узел', 'gaz': 'газ',
           'gas': 'газ', 'no': 'НЕТ', 'нет.': 'НЕТ', 'узел.': 'узел',
           'net': 'НЕТ', 'нет': 'НЕТ', 'машина.': 'машина'}.get(vid.lower(), vid)
    tip = (d.get('tip') or '').strip()
    sost = (d.get('sostoyanie') or '').strip()
    st_tip, st_sost, st_park = bylo[fid]
    if vid not in ('машина', 'узел', 'расходник', 'газ', 'НЕТ'):
        sch['vid не из списка: %s' % (vid or 'пусто')] += 1
        continue
    sch[vid] += 1
    if vid == 'НЕТ':
        novyy_tip, park = 'НЕ НАША МАШИНА', 0
    else:
        park = 1
        novyy_tip = tip if tip in NASHI else st_tip
        if vid == 'газ' and tip not in NASHI:
            # покупает газ, но какой именно — из состояния/текста не следует: не выдумываем
            novyy_tip = st_tip
    if vid == 'газ':
        sost = 'покупает ГАЗ'
    if novyy_tip != st_tip:
        peremeny['тип изменён'] += 1
    if park != st_park:
        peremeny['выведено из парка' if park == 0 else 'возвращено в парк'] += 1
    pravki.append((novyy_tip, sost or st_sost, vid, park,
                   ' | сверка: было «%s», стало vid=%s tip=%s; %s'
                   % (st_tip, vid, novyy_tip, (d.get('pochemu') or '')[:150]), fid))

cur.executemany('update fakt set tip=?, sostoyanie=?, vid_fakta=?, v_parke=?, '
                'pochemu=substr(coalesce(pochemu,"") || ?, 1, 900) where id=?', pravki)
p.commit()
print()
print('=== ЧТО СКАЗАЛА СВЕРКА ===')
for k, v in sch.most_common():
    print('  %-34s %6d  %3d%%' % (k, v, round(100 * v / max(1, len(verdikty)))))
print()
print('=== ЧТО ИЗМЕНИЛОСЬ В БАЗЕ ===')
for k, v in peremeny.most_common():
    print('  %-34s %6d' % (k, v))

cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПОЛНАЯ сверка типов провайдером -> park.db',
             len(bylo), len(pravki), len(bylo) - len(pravki),
             json.dumps({'vid': dict(sch), 'перемены': dict(peremeny),
                         'не сверено': len(bylo) - len(pravki)}, ensure_ascii=False)))
p.commit()

q = lambda s: cur.execute(s).fetchone()[0]
print()
print('=== СОСТОЯНИЕ ===')
print('  фактов всего  %6d | в парке %6d | выведено %6d'
      % (q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
         q('select count(*) from fakt where v_parke=0')))
print('  ИНН в парке   %6d' % q('select count(distinct inn) from fakt where v_parke=1'))
print()
print('  по оси vid_fakta:')
for r in cur.execute("select vid_fakta, count(*), count(distinct inn) from fakt "
                     "group by vid_fakta order by 2 desc").fetchall():
    print('    %-12s фактов %6d  ИНН %5d' % (r[0] or '(не сверено)', r[1], r[2]))
print()
print('  НОМЕНКЛАТУРА (только vid_fakta=машина), ИНН:')
for r in cur.execute("select tip, count(distinct inn) from fakt where v_parke=1 and "
                     "vid_fakta='машина' group by tip order by 2 desc limit 15").fetchall():
    print('    %-26s %5d' % (r[0] or '(пусто)', r[1]))
print()
print('  ЦЕЛЕВОЙ ПОКУПАТЕЛЬ ГАЗА (vid_fakta=газ): ИНН',
      q("select count(distinct inn) from fakt where vid_fakta='газ'"))
p.close()
