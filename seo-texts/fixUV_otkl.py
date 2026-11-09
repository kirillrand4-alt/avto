# -*- coding: utf-8 -*-
r"""fixUV (09.11): панель Meyer – отключить вход уволившемуся Волкову (meyer4).

Владелец 09.11: «выкинь того, кто уже не работает, из статистик админа/ропа» и «ну не оставляй вход тогда».
Отключённый (users.is_active=0) не входит в панель (вход проверяет is_active=1) и сам пропадает из
статистики админа и из команды руководителя (_statblok и _fixV_komanda берут только действующих). Его компании
уже розданы (fixVR, у него 0). Записи Волкова (статусы, комментарии, журнал) остаются в базе. Копия базы –
C:\centro2\_bekap\fixUV-<время>\.

    python3 zapusk_na_servere.py fixUV_otkl.py            # показать, без записи
    python3 zapusk_na_servere.py fixUV_otkl.py --primenit
Включить обратно: UPDATE users SET is_active=1 WHERE username='meyer4'
"""
import os
import sqlite3
import sys
import time

KOREN = r'C:\centro2'
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
KTO = 'meyer4'

s = sqlite3.connect(SALES, timeout=30)
r = s.execute('SELECT username, fio, role, is_active FROM users WHERE username=?', (KTO,)).fetchone()
print('сейчас:', r)
print('назначено ему компаний:', s.execute('SELECT COUNT(*) FROM company_assignment WHERE username=?', (KTO,)).fetchone()[0])
if not r or r[2] != 'sales':
    raise SystemExit('не тот пользователь – остановка')
if '--primenit' not in sys.argv:
    print('ничего не записано')
    raise SystemExit(0)
papka = os.path.join(KOREN, '_bekap', 'fixUV-' + time.strftime('%Y%m%d-%H%M%S'))
os.makedirs(papka, exist_ok=True)
b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1.db'))
s.backup(b)
b.close()
n = s.execute("UPDATE users SET is_active=0, updated_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now') "
              "WHERE username=? AND role='sales'", (KTO,)).rowcount
s.commit()
print('ЗАПИСАНО: строк %d; теперь %s; копия базы %s' % (
    n, s.execute('SELECT username, fio, is_active FROM users WHERE username=?', (KTO,)).fetchone(), papka))
print("включить обратно: UPDATE users SET is_active=1 WHERE username='%s'" % KTO)
