# -*- coding: utf-8 -*-
"""Удалить тестовые действия владельца (08.10: «удали мои тестовые действия из статистики, в
очереди 599, сделай 600»). Все они – по ООО «МАМИДА» (ИНН 9722026727) от meyer1: две отметки,
два комментария («…тест», «возвращена в очередь»), статус. Удаляются ТОЛЬКО эти строки (по
ИНН и времени теста); перед этим – копия базы продаж. Затем проверка статистики."""
import os, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
INN = '9722026727'
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa
    import logging, warnings, re
    warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    with TestClient(vnutr) as k:
        t = k.get('/obzvon-meyer/centro/stats').text
        m = re.search(r'<tr class="itog"><td>Все продавцы</td>(.*?)</tr>', t, re.S)
        yach = re.findall(r'<td[^>]*>(?:<a [^>]*>)?(\d+)', m.group(1)) if m else []
        print('строка «Все продавцы» (за сегодня: в работу, не понр., дубль, в очереди | за всё время: …):', yach)
        print('лента: %s' % ('пусто' if 'За период действий нет' in t else 'есть записи'))
        n = re.search(r'<b class="total-count">(\d+) компаний</b>', k.get('/obzvon-meyer/centro').text)
        print('«Вся очередь»: %s' % (n.group(1) if n else '?'))
    raise SystemExit(0)
B = os.path.join(KOREN, '_bekap', time.strftime('udalit-testy-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
s = sqlite3.connect(SALES)
d = sqlite3.connect(os.path.join(B, 'centro_sales_meyer1.db'))
s.backup(d)
d.close()
kto = s.execute("select distinct username from activity_log where inn<>? or username<>'meyer1'", (INN,)).fetchall()
if kto:
    print('В ЖУРНАЛЕ ЕСТЬ ДЕЙСТВИЯ НЕ ПО ТЕСТУ – не трогаю ничего: %s' % kto)
    raise SystemExit(1)
n1 = s.execute("delete from activity_log where inn=? and username='meyer1' and created_at like '2026-10-08%'", (INN,)).rowcount
n2 = s.execute("delete from company_comment where inn=? and username='meyer1' and created_at like '2026-10-08%'", (INN,)).rowcount
n3 = s.execute("delete from company_state where inn=? and username='meyer1'", (INN,)).rowcount
s.commit()
print('удалено: журнал %d, комментарии %d, статус %d; бэкап %s' % (n1, n2, n3, B))
print('осталось: журнал %d, комментарии %d, статусы %d' % tuple(s.execute('select count(*) from %s' % t).fetchone()[0]
                                                        for t in ('activity_log', 'company_comment', 'company_state')))
s.close()
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True, timeout=600, cwd=KOREN,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
print(r.stdout.decode('utf-8', 'replace')[-1500:])
if r.returncode:
    print(r.stderr.decode('utf-8', 'replace')[-1500:])
