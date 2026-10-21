# -*- coding: utf-8 -*-
r"""fixKR (21.10): панель КЦ – компании user3 поровну между user1 и user2 (владелец: «давай юзера 3 распотрошим в равных
долях»). Порядок – по баллу очереди «змейкой» (качество поровну), группа холдинга – целиком одному. Прежний владелец –
в колонке company_assignment.vladelec_do_fixKR (откат одной командой), копия базы – C:\seostat\_bekap\fixKR-<время>\,
журнал – на дроп. Статусы, комментарии и журнал действий не трогаются.

    python3 zapusk_na_servere.py fixKR_razdel.py            # план без записи
    python3 zapusk_na_servere.py fixKR_razdel.py --primenit
"""
import collections
import glob
import io
import json
import os
import sqlite3
import sys
import time

SALES = r'C:\seostat\data\centro_sales.db'
OT, KOMU = 'user3', ('user1', 'user2')
VREMYA = time.strftime('%Y%m%d-%H%M%S')

s = sqlite3.connect(SALES, timeout=30)
s.row_factory = sqlite3.Row
kol = [r[1] for r in s.execute('PRAGMA table_info(company_assignment)')]
print('колонки назначения:', kol)
sk = 'assignment_score' if 'assignment_score' in kol else None
rows = [dict(r) for r in s.execute('SELECT * FROM company_assignment WHERE username=?', (OT,))]
print('у %s назначений: %d' % (OT, len(rows)))
# холдинги: ищем каталог КЦ с holding_chlen
hold = {}
for p in glob.glob(r'C:\seostat\data\*.db'):
    try:
        k = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
        if k.execute("SELECT 1 FROM sqlite_master WHERE name='holding_chlen'").fetchone():
            hk = [r[1] for r in k.execute('PRAGMA table_info(holding_chlen)')]
            gk = next((c for c in hk if c in ('holding_id', 'gruppa', 'holding', 'gruppa_id')), None)
            if gk:
                hold.update({str(a): str(b) for a, b in k.execute('SELECT inn, %s FROM holding_chlen' % gk)})
                print('холдинги: %s (%s), записей %d' % (os.path.basename(p), gk, len(hold)))
    except sqlite3.Error:
        pass
# скрытые целиком (hidden_item kind=company, скрывал админ – общее для всех) делим отдельно от видимых: «поровну» – по
# тому, что панель показывает менеджеру (владелец: «там не 704 компании, часть панель отсекает»)
skryto = {r[0] for r in s.execute("SELECT DISTINCT inn FROM hidden_item WHERE kind='company'")}
plan, sch, ball, vid = {}, collections.Counter(), collections.Counter(), collections.Counter()
for nabor in ([r for r in rows if r['inn'] not in skryto], [r for r in rows if r['inn'] in skryto]):
    gruppy = collections.OrderedDict()
    for r in sorted(nabor, key=lambda r: -(float(r.get(sk) or 0) if sk else 0)):
        gruppy.setdefault(hold.get(r['inn']) or ('#' + r['inn']), []).append(r)
    sch_n = collections.Counter()
    for g, chleny in gruppy.items():       # группу – тому, у кого в этом наборе меньше (при равенстве – меньше балл)
        kto = min(KOMU, key=lambda u: (sch_n[u], ball[u]))
        for r in chleny:
            plan[r['inn']] = kto
            sch[kto] += 1
            sch_n[kto] += 1
            vid[kto] += r['inn'] not in skryto
            ball[kto] += float(r.get(sk) or 0) if sk else 0
print('план: всего %s, из них видимых %s; сумма балла %s' % (dict(sch), dict(vid), {u: round(b, 1) for u, b in ball.items()}))
print('видимых после:', {u: s.execute("SELECT COUNT(*) FROM company_assignment WHERE username=? AND inn NOT IN (SELECT inn FROM hidden_item "
                                      "WHERE kind='company')", (u,)).fetchone()[0] + vid[u] for u in KOMU})
deystv = {}
for t in ('company_state', 'company_comment', 'activity_log', 'hidden_item'):
    try:
        deystv[t] = s.execute('SELECT COUNT(DISTINCT inn) FROM %s WHERE inn IN (SELECT inn FROM company_assignment WHERE username=?)' % t,
                              (OT,)).fetchone()[0]
    except sqlite3.OperationalError:
        pass
print('у компаний user3 есть записи (компаний):', deystv)
print('сейчас всего:', dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall()))
if '--primenit' not in sys.argv:
    print('\nПЛАН: ничего не записано')
    raise SystemExit(0)
papka = os.path.join(r'C:\seostat\_bekap', 'fixKR-' + VREMYA)
os.makedirs(papka, exist_ok=True)
b = sqlite3.connect(os.path.join(papka, 'centro_sales.db'))
s.backup(b)
b.close()
if 'vladelec_do_fixKR' not in kol:
    s.execute('ALTER TABLE company_assignment ADD COLUMN vladelec_do_fixKR TEXT')
s.execute('BEGIN IMMEDIATE')
try:
    for inn, kto in plan.items():
        n = s.execute('UPDATE company_assignment SET vladelec_do_fixKR=username, username=? WHERE inn=? AND username=?',
                      (kto, inn, OT)).rowcount
        if n != 1:
            raise SystemExit('строка %s изменилась – откат' % inn)
    s.execute('COMMIT')
except BaseException:
    s.execute('ROLLBACK')
    raise
io.open(r'C:\seostat\drop\drop-storage\fixKR-razdel-zhurnal-%s.json' % VREMYA, 'w', encoding='utf-8').write(
    json.dumps({'ot': OT, 'plan': plan}, ensure_ascii=False))
print('\nЗАПИСАНО. теперь:', dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall()),
      '; копия базы', papka, '; откат: UPDATE company_assignment SET username=vladelec_do_fixKR WHERE vladelec_do_fixKR IS NOT NULL')
