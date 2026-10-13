# -*- coding: utf-8 -*-
"""Владелец 13.10: «Основатель, директор СТМ» компании «Атланта» (Владивосток) — считать ЛПР
(первым лицом). Только этот человек (не общее правило для «основателей»). Ручной вид
contact.rol_vruchnuyu = «первое лицо»; затем флаги ЛПР/lpr_kratko компании — функцией панели
_fixE2_pereschet_lpr, балл — отдельно fixF2_ball.py --tolko-ball."""
import inspect, io, json, os, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)], capture_output=True, timeout=900,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')); sys.stderr.write(r.stderr.decode('utf-8', 'replace')[-2000:])
    raise SystemExit(r.returncode)
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
k = sqlite3.connect(KAT, timeout=60)
k.row_factory = sqlite3.Row
kand = k.execute("select c.id, c.inn, c.person, c.position, c.rol_vruchnuyu, co.predpriyatie, co.region from contact c "
                 "join company co on co.inn=c.inn where c.position like '%снователь%' and (co.predpriyatie like '%АТЛАНТ%' "
                 "or co.predpriyatie like '%Атлант%')").fetchall()
for r in kand:
    print('найдено:', dict(r))
if len(kand) != 1:
    print('ОЖИДАЛСЯ ровно 1 контакт — ничего не меняю'); raise SystemExit(1)
r = kand[0]
zh = {'id': r['id'], 'inn': r['inn'], 'bylo': r['rol_vruchnuyu'], 'stalo': 'первое лицо', 'vremya': time.strftime('%Y-%m-%d %H:%M:%S')}
with k:
    k.execute("update contact set rol_vruchnuyu='первое лицо' where id=?", (r['id'],))
io.open(os.path.join(r'C:\seostat\drop\drop-storage', 'panel-osnovatel-atlanta-zhurnal.json'), 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False))
sys.path.insert(0, KOREN); os.chdir(KOREN)
import zapusk  # noqa: F401
from app.api import routes_centro_sales as rcs
f = getattr(rcs, '_fixE2_pereschet_lpr', None)
print('пересчёт:', inspect.signature(f) if f else 'функции нет')
if f:
    try:
        print('результат:', f(r['inn']))
    except TypeError as e:
        print('вызов не подошёл:', e)
print('после:', dict(k.execute('select inn, lpr_mobilnyy, lpr_s_fio, lpr_roli, lpr_kratko from company where inn=?', (r['inn'],)).fetchone()))
