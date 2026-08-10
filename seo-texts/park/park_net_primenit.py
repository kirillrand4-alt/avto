# -*- coding: utf-8 -*-
"""Возвращаем в парк факты, исключённые ОШИБОЧНО.

Первый проход (gemini) пометил 11 913 фактов «к нашей номенклатуре отношения не имеет»,
и по этой пометке они выпадали из выдачи. Встречная проверка ДРУГОЙ моделью
(claude-fable-5), где вопрос перевёрнут — «найди ошибку в исключении», а не «какой тип», —
показывает около 16% ошибок: реальные компрессоры, ГПА, воздуходувки, ресиверы.

Правило, записанное в журнал по итогам: разметка типа одним голосом допустима, ошибку
правит следующий проход; УДАЛЕНИЕ одним голосом недопустимо — факта в выдаче просто нет,
и никто не знает, что он там был.

Здесь применяем только вердикт ОШИБКА и только к фактам, которые сейчас исключены.
Старое состояние пишем в pravka_isklyucheniya — правку можно проверить и откатить.
"""
import sqlite3, json, os, glob, collections

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS pravka_isklyucheniya(
  fakt_id INTEGER PRIMARY KEY, bylo_vid TEXT, stalo_vid TEXT,
  bylo_tip TEXT, stalo_tip TEXT, bylo_v_parke INTEGER,
  pochemu TEXT, model_proverki TEXT, ts TEXT);
""")

VIDY = {'машина', 'узел', 'расходник', 'газ'}
dan, dubli = {}, 0
for f in sorted(glob.glob(os.path.join(D, 'park_net_proverka*.jsonl'))):
    for ln in open(f, encoding='utf-8'):
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if d.get('id') in dan:
            dubli += 1
            continue
        dan[d['id']] = d

osh = [d for d in dan.values() if str(d.get('isklyuchenie', '')).upper().startswith('ОШИБК')]
print('проверено исключений: %d (дублей в файлах %d) | признано ОШИБКОЙ: %d (%.0f%%)'
      % (len(dan), dubli, len(osh), 100.0 * len(osh) / max(1, len(dan))))

vernuto, propushcheno = 0, collections.Counter()
for d in osh:
    row = cur.execute('select vid_fakta, tip, v_parke from fakt where id=?',
                      (d['id'],)).fetchone()
    if not row:
        propushcheno['факта нет в базе'] += 1
        continue
    bylo_vid, bylo_tip, bylo_park = row
    if bylo_vid != 'НЕТ':
        propushcheno['уже не исключён'] += 1
        continue
    vid = (d.get('vid') or '').strip().lower()
    vid = {'mashina': 'машина', 'uzel': 'узел', 'rashodnik': 'расходник', 'gaz': 'газ',
           'машина.': 'машина', 'узел.': 'узел'}.get(vid, vid)
    if vid not in VIDY:
        # вид не назван — но ошибка признана; машина это или узел, решит следующий проход
        vid = 'машина'
        propushcheno['вид не назван, принят «машина»'] += 1
    tip = (d.get('tip') or '').strip()
    cur.execute('insert or replace into pravka_isklyucheniya values (?,?,?,?,?,?,?,?,datetime("now"))',
                (d['id'], bylo_vid, vid, bylo_tip, tip or bylo_tip, bylo_park,
                 (d.get('pochemu') or '')[:200], 'claude-fable-5, вопрос перевёрнут'))
    cur.execute('update fakt set vid_fakta=?, tip=case when ?<>"" then ? else tip end, '
                'v_parke=1 where id=?', (vid, tip, tip, d['id']))
    vernuto += 1
p.commit()
print('возвращено в парк: %d | пропущено: %s' % (vernuto, dict(propushcheno)))

print('\n=== БАЗА ПОСЛЕ ВОЗВРАТА ===')
for q, t in [("select count(*) from fakt", 'фактов'),
             ("select count(*) from fakt where v_parke=1", 'в парке'),
             ("select count(distinct inn) from fakt where v_parke=1", 'ИНН в парке'),
             ("select count(*) from fakt where vid_fakta='НЕТ'", 'исключено'),
             ("select count(*) from pravka_isklyucheniya", 'записей в журнале возвратов')]:
    print('  %-30s %s' % (t, cur.execute(q).fetchone()[0]))
print('\n  типы возвращённых:',
      dict(cur.execute("""select stalo_tip, count(*) from pravka_isklyucheniya
                          group by stalo_tip order by count(*) desc limit 10""").fetchall()))
p.close()
