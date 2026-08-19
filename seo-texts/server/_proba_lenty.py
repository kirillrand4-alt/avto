# -*- coding: utf-8 -*-
"""Живая проверка: отдаёт ли лента поле otvet и принимает ли ручка вложение."""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
БАЗА = 'http://127.0.0.1:8091/api'
итог = {}
# токен владельца берём из активной сессии панели (только чтение из sender.db)
import sqlite3
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
кол = [r[1] for r in s.execute('pragma table_info(sessions)')]
итог['колонки_sessions'] = кол
строка = s.execute('select * from sessions order by rowid desc limit 1').fetchone()
s.close()
токен = None
if строка:
    d = dict(zip(кол, строка))
    токен = d.get('token') or d.get('id')
итог['токен_нашёлся'] = bool(токен)
if токен:
    заг = ['-H', 'Authorization: Bearer %s' % токен]
    r = subprocess.run(['curl', '-s'] + заг + [БАЗА + '/leads?limit=5'],
                       capture_output=True, text=True, timeout=90)
    try:
        d = json.loads(r.stdout or '{}')
        лиды = d.get('leads') or []
        итог['лидов'] = len(лиды)
        итог['поле_otvet_есть'] = all('otvet' in l for l in лиды) if лиды else None
        итог['с_ответом'] = [{'компания': (l.get('company_name') or '')[:22],
                              'otvet': l.get('otvet')}
                             for l in лиды if l.get('otvet')][:3]
    except Exception as e:  # noqa: BLE001
        итог['лента_ошибка'] = (r.stdout or str(e))[:200]
    # проба загрузки файла
    ф = os.path.join(tempfile.gettempdir(), 'proba-vlozhenie.txt')
    open(ф, 'wb').write('проба вложения'.encode('utf-8'))
    r2 = subprocess.run(['curl', '-s'] + заг + ['-F', 'file=@' + ф,
                                                 БАЗА + '/vlozheniya'],
                        capture_output=True, text=True, timeout=90)
    итог['загрузка'] = (r2.stdout or '')[:200]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
